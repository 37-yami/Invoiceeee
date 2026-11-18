# -*- coding: utf-8 -*-
"""汇总 API 测试:preview 合计、docx/csv 生成、空选择拒绝、settings 默认。"""
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
from tests.util import make_png
from web.server import make_server


class ReportApiTestCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.db = Database(str(self.ws.db_path))
        self.db.init_schema()
        self.addCleanup(self.db.close)
        # 三张已确认票据
        self.ids = []
        for amount, cat in [(1234.5, "高铁/铁路"), (88.0, "餐饮"),
                            (0.01, "网约车")]:
            f = self.ws.uploads_dir / f"{len(self.ids)}.png"
            f.write_bytes(make_png())
            self.ids.append(self.db.insert_invoice(Invoice(
                original_path=str(f), category=cat, amount=amount,
                invoice_date="2026-11-01", merchant="X",
                status="confirmed")).id)
        self.server = make_server(self.ws, self.db, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def post(self, path: str, body: dict):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(req, timeout=5)

    def test_preview_returns_count_and_decimal_total(self):
        with self.post("/api/report/preview", {"ids": self.ids}) as resp:
            data = json.loads(resp.read())
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["total"], "1322.51")
        self.assertEqual(len(data["items"]), 3)

    def test_docx_endpoint_streams_attachment(self):
        meta = dict(name="张三", student_id="20261234", project="课题组A",
                    date_from="2026-11-01", date_to="2026-11-18",
                    reason="学术会议")
        with self.post("/api/report/docx",
                       {"ids": self.ids, "meta": meta}) as resp:
            self.assertEqual(resp.status, 200)
            disposition = resp.headers.get("Content-Disposition", "")
            from urllib.parse import unquote
            self.assertIn(".docx", unquote(disposition))
            data = resp.read()
        self.assertEqual(data[:2], b"PK")  # docx 即 zip
        # 工作区 exports 里也能找到同一份文件
        self.assertTrue(list(self.ws.exports_dir.glob("*.docx")))

    def test_csv_endpoint_streams_attachment(self):
        with self.post("/api/report/csv", {"ids": self.ids}) as resp:
            self.assertEqual(resp.status, 200)
            self.assertTrue(resp.read().startswith(b"\xef\xbb\xbf"))

    def test_empty_ids_rejected(self):
        for path in ("/api/report/preview", "/api/report/docx",
                     "/api/report/csv"):
            with self.subTest(path=path):
                try:
                    self.post(path, {"ids": []})
                    self.fail("应当 400")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 400)

    def test_docx_meta_falls_back_to_settings(self):
        self.db.set_setting("default_name", "李四")
        self.db.set_setting("default_student_id", "123")
        self.db.set_setting("default_project", "课题组B")
        with self.post("/api/report/docx", {"ids": self.ids}) as resp:
            disposition = resp.headers.get("Content-Disposition", "")
            from urllib.parse import unquote
            self.assertIn("李四", unquote(disposition))


if __name__ == "__main__":
    unittest.main()
