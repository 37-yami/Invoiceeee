# -*- coding: utf-8 -*-
"""本地 Web 服务器:路由、静态文件、JSON 与 multipart(Python 3.13 已移除 cgi)。

默认只监听 127.0.0.1;--lan 模式由 app.py 传入 access_code 并校验(见 Task 8)。
"""
from __future__ import annotations

import email.parser
import email.policy
import hashlib
import ipaddress
import json
import mimetypes
import re
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core import report_csv, report_docx
from core.archiver import archive, sanitize_filename, to_trash
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
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 单次上传体积上限


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
        if not target.is_relative_to(STATIC_DIR.resolve()):
            self._send_json(404, {"error": "未找到"})
            return
        self._send_file(target)

    # ---- 访问码(LAN 模式) ----
    OPEN_PATHS = ("/", "/api/access-info")

    def _needs_gate(self, path: str) -> bool:
        return not (path in self.OPEN_PATHS
                    or path.startswith("/static/"))

    def _check_access(self) -> bool:
        """未启用访问码或本机回环 → 放行;其余需 X-Access-Code 或 ?code=。"""
        if not self.access_code:
            return True
        ip = self.client_address[0]
        if ip in ("127.0.0.1", "::1"):
            return True
        supplied = self.headers.get("X-Access-Code")
        if not supplied:
            supplied = parse_qs(urlparse(self.path).query).get(
                "code", [None]
            )[0]
        return supplied == self.access_code

    def _host_ok(self) -> bool:
        """Host 头必须指向本机:回环名,或 LAN 模式下的 IP 字面量。

        防 DNS rebinding:攻击者域名解析到 127.0.0.1 时,Host 是域名而非
        回环名/IP 字面量,直接拒绝。
        """
        host = (self.headers.get("Host") or "").lower()
        host = host.rsplit(":", 1)[0].strip("[]")
        if host in ("127.0.0.1", "localhost", "::1"):
            return True
        if self.access_code:  # LAN 模式:手机直连本机局域网 IP
            try:
                ipaddress.ip_address(host)
                return True
            except ValueError:
                return False
        return False

    def _origin_ok(self) -> bool:
        """非 GET 请求的跨站防护(localhost CSRF)。

        带 Origin 头则必须与 Host 同源;否则看 Sec-Fetch-Site;
        两者都无(本地脚本/老工具)放行。
        """
        origin = self.headers.get("Origin")
        if origin:
            netloc = urlparse(origin).netloc.lower()
            host_header = (self.headers.get("Host") or "").lower()
            return netloc == host_header
        site = (self.headers.get("Sec-Fetch-Site") or "").lower()
        return site != "cross-site"

    def _gate(self, path: str, method: str = "GET") -> bool:
        """返回 False 表示已发送错误响应,调用方应立即 return。"""
        if not self._host_ok():  # Host 校验对所有路径生效(防 rebinding)
            self._send_json(403, {"error": "拒绝访问"})
            return False
        if self._needs_gate(path):
            if not self._check_access():
                self._send_json(401, {"error": "需要访问码"})
                return False
            if method != "GET" and not self._origin_ok():
                self._send_json(403, {"error": "拒绝跨站请求"})
                return False
        return True

    # ---- 路由辅助 ----
    @staticmethod
    def _match_invoice_path(path: str):
        """匹配 /api/invoices/{id} 与 /api/invoices/{id}/force-keep。"""
        prefix = "/api/invoices/"
        if not path.startswith(prefix):
            return None
        rest = path[len(prefix):]
        if rest.endswith("/force-keep"):
            action, rest = "force-keep", rest[: -len("/force-keep")]
        else:
            action = None
        if not rest.isdigit():
            return None
        return int(rest), action

    # ---- GET ----
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if not self._gate(path, self.command):
                return
            if path == "/":
                self._serve_static("index.html")
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
            elif path == "/api/invoices":
                self._api_list(parse_qs(parsed.query))
            elif path == "/api/access-info":
                self._send_json(200, {"require_code": bool(self.access_code)})
            elif path == "/api/settings":
                keys = ("default_name", "default_student_id",
                        "default_project", "ocr_cmd")
                self._send_json(200, {k: self.db.get_setting(k) or ""
                                      for k in keys})
            elif path.startswith("/image/"):
                self._serve_image(path)
            elif self._match_invoice_path(path):
                invoice_id, _ = self._match_invoice_path(path)
                inv = self.db.get_invoice(invoice_id)
                if inv:
                    self._send_json(200, inv.to_dict())
                else:
                    self._send_json(404, {"error": "票据不存在"})
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


    # ---- POST / PUT / DELETE ----
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if not self._gate(path, self.command):
                return
            match = self._match_invoice_path(path)
            if path == "/api/upload":
                self._api_upload()
            elif path == "/api/report/preview":
                self._api_report_preview()
            elif path in ("/api/report/docx", "/api/report/csv"):
                self._api_report_generate(path.rsplit("/", 1)[-1])
            elif match and match[1] == "force-keep":
                self._api_force_keep(match[0])
            else:
                self._read_body()
                self._send_json(404, {"error": "未找到"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self._send_json(500, {"error": f"服务错误: {e}"})

    # ---- 报表 ----
    def _report_meta(self, body: dict) -> dict:
        """请求 meta 优先,缺项用设置页默认值。"""
        meta = body.get("meta") or {}
        return {
            "name": meta.get("name")
                or self.db.get_setting("default_name") or "",
            "student_id": meta.get("student_id")
                or self.db.get_setting("default_student_id") or "",
            "project": meta.get("project")
                or self.db.get_setting("default_project") or "",
            "date_from": meta.get("date_from", ""),
            "date_to": meta.get("date_to", ""),
            "reason": meta.get("reason", ""),
        }

    def _api_report_preview(self):
        body = self.read_json()
        ids = body.get("ids") or []
        invoices = self.db.invoices_by_ids(ids)
        if not invoices:
            self._send_json(400, {"error": "未选择票据"})
            return
        total = sum(
            (Decimal(str(i.amount)) for i in invoices
             if i.amount is not None),
            Decimal("0"),
        )
        self._send_json(200, {
            "count": len(invoices),
            "total": f"{total:.2f}",
            "items": [i.to_dict() for i in invoices],
        })

    def _api_report_generate(self, kind: str):
        body = self.read_json()
        invoices = self.db.invoices_by_ids(body.get("ids") or [])
        if not invoices:
            self._send_json(400, {"error": "未选择票据"})
            return
        meta = self._report_meta(body)
        if kind == "docx":
            out = report_docx.generate(self.ws, invoices, meta)
        else:
            out = report_csv.generate_csv(self.ws, invoices, meta)
        self.ws.log_action("report", kind=kind, count=len(invoices))
        self._send_file(out, download_name=out.name)

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
            if not self._gate(path, self.command):
                return
            match = self._match_invoice_path(path)
            if match and match[1] is None:
                self._api_update_invoice(match[0])
            elif path == "/api/settings":
                self._api_put_settings()
            else:
                self._read_body()
                self._send_json(404, {"error": "未找到"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self._send_json(500, {"error": f"服务错误: {e}"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        try:
            if not self._gate(path, self.command):
                return
            match = self._match_invoice_path(path)
            if match and match[1] is None:
                self._api_delete_invoice(match[0])
            else:
                self._read_body()
                self._send_json(404, {"error": "未找到"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self._send_json(500, {"error": f"服务错误: {e}"})

    _EDITABLE_TEXT_FIELDS = (
        "merchant", "invoice_no", "reimburse_by",
        "project", "trip_reason", "note",
    )

    def _api_update_invoice(self, invoice_id: int):
        inv = self.db.get_invoice(invoice_id)
        if not inv:
            self._send_json(404, {"error": "票据不存在"})
            return
        body = self.read_json()
        for field in self._EDITABLE_TEXT_FIELDS:
            if field in body:
                value = body[field]
                inv.__setattr__(
                    field, value.strip() if isinstance(value, str) else ""
                )
        if "category" in body:
            if body["category"] in CATEGORIES or body["category"] == CATEGORY_UNKNOWN:
                inv.category = body["category"]
        if "invoice_date" in body:
            date = (body["invoice_date"] or "").strip()
            if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                self._send_json(400, {"error": "日期格式应为 YYYY-MM-DD"})
                return
            inv.invoice_date = date
        if "amount" in body:
            try:
                inv.amount = None if body["amount"] in (None, "") \
                    else float(body["amount"])
            except (TypeError, ValueError):
                self._send_json(400, {"error": "金额格式不正确"})
                return
        if "status" in body:
            if body["status"] == STATUS_CONFIRMED:
                inv.status = STATUS_CONFIRMED
            elif body["status"] == "pending":
                inv.status = "pending"
        # 已确认票据必须挂具体类别:文件已按类别归档,悬空会造成目录错位
        if inv.status == STATUS_CONFIRMED and inv.category == CATEGORY_UNKNOWN:
            self._send_json(
                400,
                {"error": "已确认票据需选择具体类别(不能为待定)"},
            )
            return
        # 确认或已确认记录字段变更 → (重新)归档
        if inv.status == STATUS_CONFIRMED and inv.category != CATEGORY_UNKNOWN:
            archive(self.ws, inv, self.db)
        self.db.update_invoice(inv)
        self.ws.log_action("edit", invoice_id=inv.id, category=inv.category)
        self._send_json(200, inv.to_dict())

    def _api_delete_invoice(self, invoice_id: int):
        inv = self.db.get_invoice(invoice_id)
        if not inv:
            self._send_json(404, {"error": "票据不存在"})
            return
        to_trash(self.ws, inv, self.db)
        self.db.delete_invoice(invoice_id)
        self.ws.log_action("delete", invoice_id=invoice_id)
        self._send_json(200, {"ok": True})

    def _api_force_keep(self, invoice_id: int):
        inv = self.db.get_invoice(invoice_id)
        if not inv:
            self._send_json(404, {"error": "票据不存在"})
            return
        inv.dup_flag, inv.dup_of = 0, None
        self.db.update_invoice(inv)
        self.ws.log_action("force_keep", invoice_id=invoice_id)
        self._send_json(200, inv.to_dict())

    def _api_put_settings(self):
        body = self.read_json()
        allowed = ("default_name", "default_student_id",
                   "default_project", "ocr_cmd")
        for key in allowed:
            if key in body:
                value = body[key]
                self.db.set_setting(
                    key, value.strip() if isinstance(value, str) else ""
                )
        self.ws.log_action("settings", changed=sorted(
            k for k in body if k in allowed))
        self._send_json(200, {"ok": True})

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
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD_BYTES:
            # 不读超限请求体,直接拒绝并断开(LAN 模式的防御上限)
            self.close_connection = True
            self._send_json(413, {"error": "上传内容过大,单次上限 20MB"})
            return
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
