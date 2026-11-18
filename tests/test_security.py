# -*- coding: utf-8 -*-
"""请求来源安全测试:Host 校验(防 DNS rebinding)、跨站写请求拒绝。"""
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


class SecurityTestCase(unittest.TestCase):
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

    def request(self, method: str, path: str, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else b""
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method=method,
            headers=headers or {},
        )
        return urllib.request.urlopen(req, timeout=5)


class TestHostAndOrigin(SecurityTestCase):
    def test_foreign_host_rejected(self):
        # DNS rebinding:攻击者域名解析到 127.0.0.1,Host 头是域名
        for host in ("evil.com", "attacker.example:8765"):
            with self.subTest(host=host):
                try:
                    self.request("GET", "/", headers={"Host": host})
                    self.fail("应当 403")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 403)

    def test_cross_origin_post_rejected(self):
        # 恶意网页 fetch 本地 API:Origin 与 Host 不一致
        try:
            self.request("POST", "/api/report/preview", body={"ids": []},
                         headers={"Origin": "http://evil.com"})
            self.fail("应当 403")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)

    def test_cross_site_marker_rejected(self):
        try:
            self.request("POST", "/api/report/preview", body={"ids": []},
                         headers={"Sec-Fetch-Site": "cross-site"})
            self.fail("应当 403")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)

    def test_same_origin_post_allowed(self):
        # 同源(Origin 与 Host 一致)放行:空 ids 得到 400 业务错,而非 403
        try:
            self.request("POST", "/api/report/preview", body={"ids": []},
                         headers={"Origin": f"http://127.0.0.1:{self.port}"})
            self.fail("空 ids 应当 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_plain_get_without_origin_allowed(self):
        with self.request("GET", "/api/invoices") as resp:
            self.assertEqual(resp.status, 200)


class StubHandler:
    """最小替身,只带来源检查需要的属性。"""

    def __init__(self, host, origin=None, fetch_site=None,
                 access_code=None, command="POST"):
        self.headers = {"Host": host}
        if origin:
            self.headers["Origin"] = origin
        if fetch_site:
            self.headers["Sec-Fetch-Site"] = fetch_site
        self.access_code = access_code
        self.command = command


class TestHostPolicyLanMode(unittest.TestCase):
    def test_lan_mode_allows_ip_literal_host(self):
        h = StubHandler("192.168.1.5:8765", access_code="123456")
        self.assertTrue(AppHandler._host_ok(h))

    def test_lan_mode_rejects_domain_host(self):
        h = StubHandler("evil.com:8765", access_code="123456")
        self.assertFalse(AppHandler._host_ok(h))

    def test_local_mode_rejects_lan_ip_host(self):
        # 未开 LAN(仅监听 127.0.0.1)时,外网 IP 形式的 Host 不应出现
        h = StubHandler("192.168.1.5:8765")
        self.assertFalse(AppHandler._host_ok(h))


if __name__ == "__main__":
    unittest.main()
