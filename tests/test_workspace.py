# -*- coding: utf-8 -*-
"""工作区测试:目录创建、操作日志。"""
import json
import tempfile
import unittest
from pathlib import Path

from core.workspace import Workspace


class TestWorkspaceEnsure(unittest.TestCase):
    def test_ensure_creates_five_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(Path(td))
            ws.ensure()
            for sub in ("invoices", "uploads", ".trash", "logs", "exports"):
                self.assertTrue((Path(td) / sub).is_dir(), f"缺少目录 {sub}")

    def test_path_properties(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(Path(td))
            self.assertEqual(ws.db_path, Path(td) / "data.db")
            self.assertEqual(ws.trash_dir, Path(td) / ".trash")


class TestLogAction(unittest.TestCase):
    def test_log_action_writes_json_line_with_meta(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Workspace(Path(td))
            ws.ensure()
            ws.log_action("upload", invoice_id=3, category="餐饮")
            log_file = Path(td) / "logs" / "app.log"
            self.assertTrue(log_file.exists())
            line = json.loads(
                log_file.read_text(encoding="utf-8").strip().splitlines()[-1]
            )
            self.assertEqual(line["action"], "upload")
            self.assertEqual(line["meta"]["invoice_id"], 3)
            # 不含全文:meta 只有所给键
            self.assertEqual(set(line["meta"].keys()), {"invoice_id", "category"})
            self.assertIn("time", line)


if __name__ == "__main__":
    unittest.main()
