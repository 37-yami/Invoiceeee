# -*- coding: utf-8 -*-
"""票据库 CRUD API 测试:确认归档、重归档、删除入回收站、强制保留。"""
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


class ApiTestCase(unittest.TestCase):
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
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        # LIFO:先 shutdown 停线程,再 server_close(顺序反了会 WinError 10038)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        return urllib.request.urlopen(req, timeout=5)

    def make_pending(self, merchant: str = "全季酒店") -> Invoice:
        f = self.ws.uploads_dir / "a.png"
        f.write_bytes(make_png())
        return self.db.insert_invoice(Invoice(
            original_path=str(f), category="酒店住宿",
            invoice_date="2026-11-02", amount=358.0, merchant=merchant))


class TestPutInvoice(ApiTestCase):
    def test_confirm_archives_file(self):
        inv = self.make_pending()
        with self.request("PUT", f"/api/invoices/{inv.id}",
                          {"status": "confirmed"}) as resp:
            self.assertEqual(resp.status, 200)
            row = json.loads(resp.read())
        self.assertEqual(row["status"], "confirmed")
        self.assertTrue(Path(row["archived_path"]).exists())
        self.assertIn("酒店住宿", row["archived_path"])
        self.assertFalse(Path(inv.original_path).exists())

    def test_change_merchant_rearchives(self):
        inv = self.make_pending()
        first = self.request(
            "PUT", f"/api/invoices/{inv.id}", {"status": "confirmed"}
        )
        first_path = json.loads(first.read())["archived_path"]
        with self.request("PUT", f"/api/invoices/{inv.id}",
                          {"merchant": "如家酒店"}) as resp:
            row = json.loads(resp.read())
        self.assertFalse(Path(first_path).exists())  # 旧归档移走
        self.assertTrue(Path(row["archived_path"]).exists())
        self.assertIn("如家酒店", row["archived_path"])

    def test_put_missing_404(self):
        try:
            self.request("PUT", "/api/invoices/999", {"status": "confirmed"})
            self.fail("应当 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_put_rejects_malformed_date(self):
        # 非法日期会产生畸形归档路径,必须 400 拒绝;空串=清空日期,允许
        inv = self.make_pending()
        for bad in ("2026/11/18", "2026年11月18日", "18-11-2026", "x"):
            with self.subTest(bad=bad):
                try:
                    self.request("PUT", f"/api/invoices/{inv.id}",
                                 {"invoice_date": bad})
                    self.fail(f"{bad} 应被拒绝")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 400)
        with self.request("PUT", f"/api/invoices/{inv.id}",
                          {"invoice_date": "2026-11-18"}) as resp:
            self.assertEqual(resp.status, 200)
        with self.request("PUT", f"/api/invoices/{inv.id}",
                          {"invoice_date": ""}) as resp:
            self.assertEqual(resp.status, 200)


class TestDeleteInvoice(ApiTestCase):
    def test_delete_moves_to_trash_and_drops_index(self):
        inv = self.make_pending()
        with self.request("PUT", f"/api/invoices/{inv.id}",
                          {"status": "confirmed"}) as resp:
            archived = json.loads(resp.read())["archived_path"]
        with self.request("DELETE", f"/api/invoices/{inv.id}") as resp:
            self.assertEqual(resp.status, 200)
        self.assertIsNone(self.db.get_invoice(inv.id))
        self.assertFalse(Path(archived).exists())
        trashed = list(self.ws.trash_dir.iterdir())
        self.assertEqual(len(trashed), 1)  # 原图在回收站

    def test_delete_pending_uploads_file_also_to_trash(self):
        inv = self.make_pending()  # 尚未归档,原图在 uploads/
        self.request("DELETE", f"/api/invoices/{inv.id}")
        self.assertFalse(Path(inv.original_path).exists())
        self.assertEqual(len(list(self.ws.trash_dir.iterdir())), 1)


class TestForceKeep(ApiTestCase):
    def test_force_keep_clears_dup_flag(self):
        inv = self.make_pending()
        inv.dup_flag, inv.dup_of = 1, 42
        self.db.update_invoice(inv)
        with self.request("POST",
                          f"/api/invoices/{inv.id}/force-keep") as resp:
            self.assertEqual(resp.status, 200)
            row = json.loads(resp.read())
        self.assertEqual(row["dup_flag"], 0)
        self.assertIsNone(row["dup_of"])


if __name__ == "__main__":
    unittest.main()
