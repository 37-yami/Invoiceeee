# -*- coding: utf-8 -*-
"""导入编排:多文件/文件夹扫描 → 入库管线(与界面解耦,可无头测试)。

管线与原 Web 上传管线等价:校验扩展 → SHA-256 → uploads 暂存 →
OCR 文本 + 文件名关键词分类 → 提取金额/日期/发票号 → 重复检测 →
类别已知即归档;字段齐全(置信 ≥0.7 且有金额或日期)自动确认。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from core.archiver import archive, sanitize_filename
from core.classifier import classify, extract_fields
from core.db import Database
from core.duplicate import find_dup_of
from core.learned import learned_lookup, learned_upsert
from core.models import (
    CATEGORIES,
    CATEGORY_UNKNOWN,
    STATUS_CONFIRMED,
    Invoice,
)
from core.ocr import OcrEngine, make_engine
from core.workspace import Workspace

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp",
              ".bmp", ".tif", ".tiff", ".gif"}
PDF_EXTS = {".pdf"}
ACCEPTED_EXTS = IMAGE_EXTS | PDF_EXTS


class Importer:
    def __init__(self, ws: Workspace, db: Database,
                 engine: OcrEngine | None = None):
        self.ws = ws
        self.db = db
        self.engine = engine if engine is not None else make_engine(db)

    # ---- 文件来源 ----
    def scan_folder(self, folder: Path) -> list[Path]:
        """递归收集图片与 PDF;目录缺失返回空;按绝对路径去重后排序。"""
        folder = Path(folder)
        if not folder.is_dir():
            return []
        seen: set[Path] = set()
        found: list[Path] = []
        for p in folder.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in ACCEPTED_EXTS:
                continue
            key = p.resolve()
            if key in seen:
                continue
            seen.add(key)
            found.append(p)
        return sorted(found)

    # ---- 导入 ----
    def import_files(self, paths: list[Path],
                     user_category: str | None = None) -> list[Invoice]:
        """导入多个文件;非票据/空文件跳过,绝不因单个文件失败中断。"""
        out: list[Invoice] = []
        for path in paths:
            path = Path(path)
            if path.suffix.lower() not in ACCEPTED_EXTS:
                continue
            if not path.is_file() or path.stat().st_size == 0:
                continue
            try:
                out.append(self._create_invoice(path, user_category))
            except Exception:
                continue  # 单文件失败不拖垮整批
        self.ws.log_action("import", count=len(out))
        return out

    def _create_invoice(self, path: Path,
                        user_category: str | None) -> Invoice:
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        inv = self.db.insert_invoice(
            Invoice(original_path="", file_hash=digest)
        )
        safe = sanitize_filename(path.stem, maxlen=40)
        saved = self.ws.uploads_dir / f"{inv.id}_{safe}{path.suffix.lower()}"
        saved.write_bytes(content)
        inv.original_path = str(saved)

        self._recognize(inv, path.stem, user_category)
        self.db.update_invoice(inv)
        self.ws.log_action(
            "import", invoice_id=inv.id, category=inv.category
        )
        return inv

    def _recognize(self, inv: Invoice, filename_stem: str,
                   user_category: str | None = None) -> None:
        """分类 + 字段提取 + 重复检测 + 归档决策(就地修改 inv)。

        识别优先级:用户显式选择(0.9)> 学到的商户规则(0.9,
        来自历史人工确认)> 关键词规则(0.7)> 文件名兜底。
        """
        text = self._extract_text(Path(inv.original_path or ""))
        text_norm = re.sub(r"\s+", "", text)
        if user_category in CATEGORIES:
            category, confidence = user_category, 0.9
        else:
            # OCR 文本在前、文件名在后:内容优先,文件名兜底
            learned = learned_lookup(self.db, text_norm)
            if learned is not None:
                category, confidence = learned
            else:
                category, confidence = classify(f"{text} {filename_stem}")
        inv.category = category

        fields = extract_fields(text)  # 字段只认文本内容,文件名不可靠
        if fields["amount"] is not None:
            inv.amount = fields["amount"]
        if fields["date"]:
            inv.invoice_date = fields["date"]
        if fields["invoice_no"]:
            inv.invoice_no = fields["invoice_no"]
        if not inv.invoice_no:
            inv.invoice_no = self._invoice_no_from_filename(
                filename_stem, text
            ) or ""

        dup = find_dup_of(self.db, inv)
        if dup is not None:
            inv.dup_flag, inv.dup_of = 1, dup

        if category != CATEGORY_UNKNOWN:
            archive(self.ws, inv, self.db)
            # 自动确认必须有金额:报销核心是金额,只有日期的说明类文件留给人工
            if confidence >= 0.7 and inv.amount is not None:
                inv.status = STATUS_CONFIRMED

    @staticmethod
    def _invoice_no_from_filename(filename_stem: str, text: str) -> str:
        """文件名锚定的发票号兜底:数电票文件名惯例含 20 位号码。

        仅当文件名里的 15-20 位号码在正文(去空白)中出现时才采用,
        防止把别的长数字张冠李戴;PDF 版式常把标签与号码拆到两处。
        """
        runs = re.findall(r"(?<!\d)(\d{15,20})(?!\d)", filename_stem)
        if not runs:
            return ""
        norm_text = re.sub(r"\s+", "", text)
        for run in runs:
            if run in norm_text:
                return run
        return ""

    def _extract_text(self, saved: Path) -> str:
        """图片走 OCR;PDF 先直接抽文本,抽不到(扫描版)渲染后走 OCR。"""
        try:
            if saved.suffix.lower() in PDF_EXTS:
                from core import invoice_pdf

                text = invoice_pdf.pdf_text(str(saved))
                if len(text.strip()) >= 12:
                    return text
                import os
                import tempfile

                fd, tmp = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                try:
                    invoice_pdf.render_page_png(str(saved), tmp)
                    return self.engine.extract(tmp)
                finally:
                    Path(tmp).unlink(missing_ok=True)
            return self.engine.extract(str(saved))
        except Exception:
            return ""

    def reimport_unknown(self) -> list[Invoice]:
        """对 pending 且 unknown 的记录重跑识别(换装 OCR 后补识别)。"""
        updated: list[Invoice] = []
        for inv in self.db.list_invoices(status="pending"):
            if inv.category != CATEGORY_UNKNOWN:
                continue
            stem = Path(inv.original_path).stem
            stem = stem.split("_", 1)[-1]  # 去掉 id 前缀还原文件名
            inv.dup_flag, inv.dup_of = 0, None
            self._recognize(inv, stem)
            self.db.update_invoice(inv)
            updated.append(inv)
        self.ws.log_action("reimport", count=len(updated))
        return updated
