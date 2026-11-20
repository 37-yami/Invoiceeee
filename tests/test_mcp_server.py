# -*- coding: utf-8 -*-
"""MCP stdio 服务器测试:协议握手、工具列表、查询/统计/生成汇总。"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def make_pdf(path: Path, lines: list[str]) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((60, 80 + i * 24), line, fontname="china-s",
                         fontsize=11)
    doc.save(str(path))
    doc.close()


class McpServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os

        cls.td = Path(tempfile.mkdtemp())
        cls.ws = cls.td / "工作区"
        from core.db import Database
        from core.workspace import Workspace
        from gui.importer import Importer

        cls.ws.mkdir(parents=True)
        cls.wsb = Workspace(cls.ws)
        cls.wsb.ensure()
        cls.db = Database(str(cls.wsb.db_path))
        cls.db.init_schema()
        # 两张文本型 PDF:免 OCR,确定性字段
        imp = Importer(cls.wsb, cls.db, engine=type("N", (), {
            "extract": staticmethod(lambda p: "")})())
        f1 = cls.td / "高铁票12306.pdf"
        make_pdf(f1, ["12306 高铁车票", "价税合计:¥288.00",
                      "开票日期:2026-09-22"])
        f2 = cls.td / "酒店住宿发票.pdf"
        make_pdf(f2, ["如家酒店住宿", "价税合计:¥200.00",
                      "开票日期:2026-09-21", "发票号码:042001900111"])
        cls.imported = imp.import_files([f1, f2])
        assert len(cls.imported) == 2

        cls.proc = subprocess.Popen(
            [sys.executable, str(REPO / "mcp_server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "BAOXIAO_WORKSPACE": str(cls.ws)},
            cwd=str(REPO),
        )

    @staticmethod
    def _env_path():
        import os

        return os.environ.get("PATH", "")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.db.close()
        shutil.rmtree(cls.td)

    def _rpc(self, payload: dict) -> dict:
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self.proc.stdin.write(line.encode("utf-8"))
        self.proc.stdin.flush()
        raw = self.proc.stdout.readline().decode("utf-8")
        return json.loads(raw)

    def test_handshake_tools_and_calls(self):
        # initialize 握手
        resp = self._rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {}})
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["serverInfo"]["name"],
                         "baoxiao-manager")
        # 通知(无 id)不应产生响应,这里只需不崩
        self.proc.stdin.write(
            (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
             + "\n").encode("utf-8"))
        self.proc.stdin.flush()

        # tools/list
        resp = self._rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(names,
                         {"query_invoices", "stats", "generate_report"})

        # tools/call: 查询
        resp = self._rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "query_invoices",
                                     "arguments": {"category": "高铁/铁路"}}})
        text = resp["result"]["content"][0]["text"]
        self.assertIn("288.00", text)
        self.assertNotIn("uploads", text)  # 不暴露本机路径

        # tools/call: 统计
        resp = self._rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                          "params": {"name": "stats", "arguments": {}}})
        text = resp["result"]["content"][0]["text"]
        self.assertIn("488.00", text)

        # tools/call: 生成汇总单
        ids = [r.id for r in self.imported]
        resp = self._rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                          "params": {"name": "generate_report",
                                     "arguments": {"ids": ids,
                                                   "meta": {"name": "测试"}}}})
        text = resp["result"]["content"][0]["text"]
        out = Path(text.splitlines()[-1].strip())
        self.assertTrue(out.exists())
        self.assertEqual(out.parent.name, "exports")

    def test_unknown_tool_error(self):
        resp = self._rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                          "params": {"name": "不存在的工具",
                                     "arguments": {}}})
        self.assertIn("error", resp)


if __name__ == "__main__":
    unittest.main()
