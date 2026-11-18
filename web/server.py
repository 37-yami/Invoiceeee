# -*- coding: utf-8 -*-
"""本地 Web 服务器:路由、静态文件、JSON 与 multipart(Python 3.13 已移除 cgi)。

默认只监听 127.0.0.1;--lan 模式由 app.py 传入 access_code 并校验(见 Task 8)。
"""
from __future__ import annotations

import email.parser
import email.policy
import hashlib
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core.archiver import archive, sanitize_filename
from core.classifier import classify, extract_fields
from core.db import Database
from core.duplicate import find_dup_of
from core.models import (
    CATEGORIES,
    CATEGORY_UNKNOWN,
    STATUS_CONFIRMED,
    Invoice,
)
from core.ocr import CliOcr, NoopOcr
from core.workspace import Workspace

STATIC_DIR = Path(__file__).parent / "static"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_multipart(body: bytes, content_type: str) -> list[tuple[str, str, bytes]]:
    """解析 multipart/form-data,返回 [(字段名, 文件名, 内容)]。

    非文件字段文件名为空串;解析失败返回空列表,不让上传阻塞。
    """
    try:
        header = (
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8")
        msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
            header + body
        )
        if not msg.is_multipart():
            return []
        parts = []
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition") or ""
            filename = part.get_filename() or ""
            content = part.get_payload(decode=True) or b""
            parts.append((str(name), str(filename), content))
        return parts
    except Exception:
        return []


class AppHandler(BaseHTTPRequestHandler):
    ws: Workspace = None  # type: ignore[assignment]
    db: Database = None  # type: ignore[assignment]
    access_code: str | None = None

    # ---- 通用工具 ----
    def log_message(self, format, *args):  # 控制台保持安静
        pass

    def _send_json(self, status: int, obj) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def read_json(self) -> dict:
        try:
            return json.loads(self._read_body().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _send_file(self, path: Path, download_name: str | None = None) -> None:
        if not path.is_file():
            self._send_json(404, {"error": "文件不存在"})
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            from urllib.parse import quote
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quote(download_name)}",
            )
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, rel: str) -> None:
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())):
            self._send_json(404, {"error": "未找到"})
            return
        self._send_file(target)

    # ---- GET ----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self._serve_static("index.html")
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
            elif path == "/api/invoices":
                self._api_list(parse_qs(parsed.query))
            elif path.startswith("/image/"):
                self._serve_image(path)
            else:
                self._send_json(404, {"error": "未找到"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # 服务器不因单请求崩溃
            self._send_json(500, {"error": f"服务错误: {e}"})

    def _api_list(self, query: dict):
        def first(key: str):
            return query.get(key, [None])[0]

        rows = self.db.list_invoices(
            status=first("status"),
            category=first("category"),
            date_from=first("date_from"),
            date_to=first("date_to"),
            q=first("q"),
        )
        self._send_json(200, [r.to_dict() for r in rows])

    def _serve_image(self, path: str):
        try:
            invoice_id = int(path.rsplit("/", 1)[-1])
        except ValueError:
            self._send_json(404, {"error": "未找到"})
            return
        inv = self.db.get_invoice(invoice_id)
        if not inv:
            self._send_json(404, {"error": "未找到"})
            return
        for candidate in (inv.archived_path, inv.original_path):
            if candidate:
                p = Path(candidate)
                if p.exists():
                    self._send_file(p)
                    return
        self._send_json(404, {"error": "图片文件缺失"})


    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/upload":
                self._api_upload()
            else:
                self._read_body()  # 消费请求体,保持连接状态干净
                self._send_json(404, {"error": "未找到"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self._send_json(500, {"error": f"服务错误: {e}"})

    def _ocr_engine(self):
        cmd = self.db.get_setting("ocr_cmd")
        return CliOcr(cmd) if cmd else NoopOcr()

    def _create_invoice(self, filename: str, content: bytes,
                        user_category: str | None) -> Invoice:
        digest = hashlib.sha256(content).hexdigest()
        ext = Path(filename).suffix.lower()
        inv = self.db.insert_invoice(
            Invoice(original_path="", file_hash=digest)
        )
        # 原图先存 uploads/,带 id 前缀防重名
        safe = sanitize_filename(Path(filename).stem, maxlen=40)
        saved = self.ws.uploads_dir / f"{inv.id}_{safe}{ext}"
        saved.write_bytes(content)
        inv.original_path = str(saved)

        # 分类:用户显式选择 > OCR 文本 + 文件名关键词
        text = self._ocr_engine().extract(str(saved))
        if user_category in CATEGORIES:
            category, confidence = user_category, 0.9
        else:
            category, confidence = classify(
                f"{text} {Path(filename).stem}"
            )
        inv.category = category

        # 字段只从 OCR 文本提取(文件名不可靠)
        fields = extract_fields(text)
        if fields["amount"] is not None:
            inv.amount = fields["amount"]
        if fields["date"]:
            inv.invoice_date = fields["date"]
        if fields["invoice_no"]:
            inv.invoice_no = fields["invoice_no"]

        dup = find_dup_of(self.db, inv)
        if dup is not None:
            inv.dup_flag, inv.dup_of = 1, dup

        # 分类明确(用户选择或关键词命中)→ 立即按类别归档;
        # 字段齐全才自动确认,否则留待确认队列
        if category != CATEGORY_UNKNOWN:
            archive(self.ws, inv, self.db)
            if confidence >= 0.7 and (
                inv.amount is not None or inv.invoice_date
            ):
                inv.status = STATUS_CONFIRMED
        self.db.update_invoice(inv)
        self.ws.log_action(
            "upload", invoice_id=inv.id, category=inv.category
        )
        return inv

    def _api_upload(self):
        parts = parse_multipart(
            self._read_body(), self.headers.get("Content-Type", "")
        )
        user_category = None
        files: list[tuple[str, bytes]] = []
        for name, filename, content in parts:
            if name == "category" and not filename:
                user_category = (
                    content.decode("utf-8", "replace").strip() or None
                )
            elif name == "files" and filename:
                files.append((filename, content))
        results = []
        for filename, content in files:
            ext = Path(filename).suffix.lower()
            if ext not in IMAGE_EXTS or not content:
                continue  # 非图片或空文件:跳过,不报错
            results.append(
                self._create_invoice(filename, content, user_category)
            )
        self._send_json(200, {"invoices": [r.to_dict() for r in results]})


def make_server(ws: Workspace, db: Database, host: str, port: int,
                access_code: str | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (AppHandler,), {
        "ws": ws, "db": db, "access_code": access_code,
    })
    return ThreadingHTTPServer((host, port), handler)
