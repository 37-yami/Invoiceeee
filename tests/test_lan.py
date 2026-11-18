# -*- coding: utf-8 -*-
"""LAN 访问码测试:本机免验、远程需码、放行静态壳与 access-info。"""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from core.db import Database
from core.workspace import Workspace
from web.server import AppHandler, make_server


class FakeHandler:
    """最小 handler 替身,只带 _check_access 需要的属性。"""

    def __init__(self, ip: str, supplied: str | None,
                 path: str = "/api/invoices", access_code: str | None = "123456"):
        self.client_address = (ip, 9999)
        self.headers = {"X-Access-Code": supplied} if supplied else {}
        self.path = path
        self.access_code = access_code


class TestCheckAccess(unittest.TestCase):
    def test_disabled_always_allows(self):
        h = FakeHandler("192.168.1.5", None, access_code=None)
        self.assertTrue(AppHandler._check_access(h))

    def test_local_loopback_bypasses_code(self):
        for ip in ("127.0.0.1", "::1"):
            h = FakeHandler(ip, None)
            self.assertTrue(AppHandler._check_access(h), f"{ip} 应免验")

    def test_remote_without_code_denied(self):
        self.assertFalse(AppHandler._check_access(
            FakeHandler("192.168.1.5", None)))

    def test_remote_with_wrong_code_denied(self):
        self.assertFalse(AppHandler._check_access(
            FakeHandler("192.168.1.5", "000000")))

    def test_remote_with_code_allowed(self):
        self.assertTrue(AppHandler._check_access(
            FakeHandler("192.168.1.5", "123456")))

    def test_remote_with_query_code_allowed(self):
        h = FakeHandler("192.168.1.5", None, path="/image/3?code=123456")
        self.assertTrue(AppHandler._check_access(h))


class TestAccessInfoEndpoint(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.db = Database(str(self.ws.db_path))
        self.db.init_schema()
        self.addCleanup(self.db.close)

    def _get(self, path: str):
        server = make_server(self.ws, self.db, "127.0.0.1", 0,
                             access_code="123456")
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        return urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=5
        )

    def test_access_info_reports_code_required(self):
        with self._get("/api/access-info") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(json.loads(resp.read()), {"require_code": True})


if __name__ == "__main__":
    unittest.main()
