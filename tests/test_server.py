# -*- coding: utf-8 -*-
"""Web 服务器核心测试:静态页、JSON API、图片、multipart 解析。"""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from core.db import Database
from core.models import Invoice
from core.workspace import Workspace
from web.server import make_server, parse_multipart


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.db = Database(str(self.ws.db_path))
        self.db.init_schema()
        self.addCleanup(self.db.close)
        self.server = make_server(self.ws, self.db, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def get(self, path: str):
        return urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}{path}", timeout=5
        )


class TestStaticAndApi(ServerTestCase):
    def test_index_serves_html(self):
        with self.get("/") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers["Content-Type"])
            body = resp.read().decode("utf-8")
            self.assertIn("学生报销管家", body)

    def test_static_css_served(self):
        with self.get("/static/style.css") as resp:
            self.assertEqual(resp.status, 200)

    def test_api_invoices_empty_list(self):
        with self.get("/api/invoices") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(json.loads(resp.read()), [])

    def test_api_invoices_passes_filters(self):
        self.db.insert_invoice(Invoice(original_path="a.jpg",
                                       category="餐饮", status="confirmed"))
        self.db.insert_invoice(Invoice(original_path="b.jpg",
                                       category="机票"))
        with self.get("/api/invoices?status=confirmed") as resp:
            rows = json.loads(resp.read())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "餐饮")

    def test_image_missing_404(self):
        try:
            self.get("/image/999")
            self.fail("应当 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_image_serves_archived_file(self):
        f = self.ws.uploads_dir / "a.jpg"
        f.write_bytes(b"fakejpg")
        inv = self.db.insert_invoice(Invoice(
            original_path=str(f), category="餐饮"))
        dest = self.ws.invoices_dir / "2026-11" / "餐饮" / "a.jpg"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"fakejpg")
        inv.archived_path = str(dest)
        self.db.update_invoice(inv)
        with self.get(f"/image/{inv.id}") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.read(), b"fakejpg")


class TestParseMultipart(unittest.TestCase):
    def test_parses_file_and_field(self):
        boundary = "----testboundary123"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="category"\r\n\r\n'
            f"餐饮\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; '
            f'filename="ticket.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode("utf-8") + b"\x89PNG-fake-bytes" + (
            f"\r\n--{boundary}--\r\n"
        ).encode("utf-8")
        parts = parse_multipart(
            body, f"multipart/form-data; boundary={boundary}"
        )
        self.assertEqual(len(parts), 2)
        names = [p[0] for p in parts]
        self.assertIn("category", names)
        file_part = next(p for p in parts if p[0] == "files")
        self.assertEqual(file_part[1], "ticket.jpg")
        self.assertEqual(file_part[2], b"\x89PNG-fake-bytes")


if __name__ == "__main__":
    unittest.main()
