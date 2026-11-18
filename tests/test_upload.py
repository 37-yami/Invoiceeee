# -*- coding: utf-8 -*-
"""上传管线测试:多图上传、类别参数、文件名规则、重复标记、脏部件。"""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from core.db import Database
from core.workspace import Workspace
from tests.util import make_png
from web.server import make_server


class UploadTestCase(unittest.TestCase):
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

    def post_multipart(self, parts: list[tuple[str, str, bytes, bool]]):
        """parts: (字段名, 文件名, 内容, 是否文件)"""
        boundary = "----uploadtest42"
        body = b""
        for name, filename, content, is_file in parts:
            body += f"--{boundary}\r\n".encode()
            if is_file:
                body += (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode("utf-8") + content + b"\r\n"
            else:
                body += (
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                ).encode("utf-8") + content + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/upload", data=body,
            headers={"Content-Type":
                     f"multipart/form-data; boundary={boundary}"},
        )
        return urllib.request.urlopen(req, timeout=5)

    def upload_files(self, entries: list[tuple[str, bytes]],
                     category: str | None = None):
        parts = [("files", name, content, True) for name, content in entries]
        if category:
            parts.append(("category", "", category.encode(), False))
        with self.post_multipart(parts) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read())["invoices"]


class TestUpload(UploadTestCase):
    def test_three_images_create_pending_records(self):
        rows = self.upload_files([
            ("a.png", make_png(color=(1, 2, 3))),
            ("b.png", make_png(color=(4, 5, 6))),
            ("c.png", make_png(color=(7, 8, 9))),
        ])
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["category"], "unknown")
            self.assertTrue(Path(row["original_path"]).exists())
        # NoopOcr:置信不足,留 uploads 不归档
        self.assertEqual(len(list(self.ws.uploads_dir.glob("*.png"))), 3)
        self.assertEqual(list(self.ws.invoices_dir.rglob("*.png")), [])

    def test_user_category_param_wins(self):
        rows = self.upload_files([("a.png", make_png())], category="酒店住宿")
        self.assertEqual(rows[0]["category"], "酒店住宿")
        # 用户显式选类:直接归档到该类别目录,仍待确认字段
        self.assertTrue(Path(rows[0]["archived_path"]).exists())
        self.assertIn("酒店住宿", rows[0]["archived_path"])

    def test_filename_rule_classifies(self):
        # OCR 不可用时按文件名规则:文件名含 12306 → 高铁/铁路
        rows = self.upload_files([("高铁票12306.png", make_png())])
        self.assertEqual(rows[0]["category"], "高铁/铁路")
        # 无日期金额:仍 pending,但按类别归档
        self.assertEqual(rows[0]["status"], "pending")
        self.assertIn("高铁-铁路", rows[0]["archived_path"])

    def test_reupload_same_file_flagged_duplicate(self):
        content = make_png(color=(9, 9, 9))
        first = self.upload_files([("x.png", content)])
        second = self.upload_files([("x_again.png", content)])
        self.assertEqual(second[0]["dup_flag"], 1)
        self.assertEqual(second[0]["dup_of"], first[0]["id"])
        self.assertEqual(first[0]["dup_flag"], 0)

    def test_dirty_parts_skipped_not_crash(self):
        # 文本字段 + 空文件部件 + 非图片扩展:只入库合法图片
        rows = self.upload_files([
            ("note.txt", b"hello"),
            ("empty.png", b""),
            ("good.png", make_png()),
        ])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["original_path"].endswith(".png"))

    def test_concurrent_uploads_all_succeed(self):
        # LAN 场景:手机+电脑同时上传,不允许 500 或残留半成品记录
        import concurrent.futures

        def upload_one(i: int):
            content = make_png(color=(i, 100 + i, 200 + i))
            return i, self.upload_files([(f"批量{i}.png", content)])

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(upload_one, range(10)))
        self.assertEqual([i for i, _ in results], list(range(10)))
        rows = self.db.list_invoices()
        self.assertEqual(len(rows), 10)
        for inv in rows:  # 无半成品:原图文件都在
            self.assertTrue(Path(inv.original_path).exists(),
                            f"票据 {inv.id} 原图缺失")

    def test_oversized_upload_rejected(self):
        # 体积上限防御(LAN 模式),超限 413 且不入库
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(
            "POST", "/api/upload", body=b"x",
            headers={
                "Content-Type": "multipart/form-data; boundary=x",
                "Content-Length": str(30 * 1024 * 1024),
            },
        )
        resp = conn.getresponse()
        self.assertEqual(resp.status, 413)
        resp.read()
        conn.close()
        self.assertEqual(len(self.db.list_invoices()), 0)


if __name__ == "__main__":
    unittest.main()
