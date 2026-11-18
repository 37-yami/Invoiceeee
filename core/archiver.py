# -*- coding: utf-8 -*-
"""归档器:原图按规则移动到 invoices/,数据库只做索引。

路径规则:invoices/YYYY-MM/类别/YYYYMMDD_商户_金额_id.ext
删除=移入 .trash/(时间戳前缀防覆盖),绝不物理删除。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from core.db import Database
from core.models import Invoice
from core.workspace import Workspace

_ILLEGAL = set('\\/:*?"<>|')


def sanitize_filename(name: str, maxlen: int = 30) -> str:
    """去 Windows 非法字符与空白;空给"未命名";限长。"""
    cleaned = "".join(ch for ch in (name or "") if ch not in _ILLEGAL)
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = "未命名"
    return cleaned[:maxlen]


def _date_parts(inv: Invoice) -> tuple[str, str]:
    """返回 (YYYY-MM, YYYYMMDD);票据日期优先,缺省用创建日期。"""
    date = inv.invoice_date or inv.created_at[:10] or ""
    if len(date) >= 10:
        return date[:7], date.replace("-", "")[:8]
    return "未知月份", "00000000"


def archive_path(ws: Workspace, inv: Invoice) -> Path:
    month, yyyymmdd = _date_parts(inv)
    ext = Path(inv.original_path or inv.archived_path or "x.jpg").suffix or ".jpg"
    filename = (
        f"{yyyymmdd}_{sanitize_filename(inv.merchant)}"
        f"_{inv.amount if inv.amount is not None else 0:.2f}"
        f"_{inv.id or 0}{ext}"
    )
    return ws.invoices_dir / month / inv.category / filename


def _unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    n = 1
    while True:
        candidate = target.with_name(f"{target.stem}_{n}{target.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def archive(ws: Workspace, inv: Invoice, db: Database) -> Path:
    """把原图(或旧归档)移动到规则路径并更新索引;返回新路径。"""
    source = None
    for candidate in (inv.archived_path, inv.original_path):
        if candidate and Path(candidate).exists():
            source = Path(candidate)
            break
    if source is None:
        raise FileNotFoundError(
            f"票据 {inv.id} 的原图不存在: {inv.original_path}"
        )
    target = _unique_path(archive_path(ws, inv))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    inv.archived_path = str(target)
    db.update_invoice(inv)
    return target


def to_trash(ws: Workspace, inv: Invoice, db: Database) -> Path:
    """原图移入 .trash/(时间戳前缀防覆盖),清空索引中的归档路径。"""
    ws.trash_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = ws.trash_dir / f"{stamp}_{inv.id or 0}_{Path(inv.original_path).name}"
    source = None
    for candidate in (inv.archived_path, inv.original_path):
        if candidate and Path(candidate).exists():
            source = Path(candidate)
            break
    if source is not None:
        shutil.move(str(source), str(dest))
    else:
        dest = ws.trash_dir / f"{stamp}_{inv.id or 0}_文件缺失"
    inv.archived_path = None
    db.update_invoice(inv)
    return dest
