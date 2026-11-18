# -*- coding: utf-8 -*-
"""OCR 适配器测试:NoopOcr、CliOcr(成功/失败降级)。"""
import unittest

from core.ocr import CliOcr, NoopOcr


class TestNoopOcr(unittest.TestCase):
    def test_extract_returns_empty(self):
        self.assertEqual(NoopOcr().extract("任意.jpg"), "")


class TestCliOcr(unittest.TestCase):
    def test_success_returns_stdout(self):
        # 模板 {image} 被替换,stdout 作为文本返回
        engine = CliOcr('cmd /c echo hello-from-ocr {image}')
        text = engine.extract("fake.png")
        self.assertIn("hello-from-ocr", text)
        self.assertIn("fake.png", text)  # 占位符确实被替换

    def test_nonzero_exit_returns_empty(self):
        engine = CliOcr("cmd /c exit 1")
        self.assertEqual(engine.extract("x.png"), "")

    def test_missing_command_returns_empty(self):
        engine = CliOcr("definitely-not-a-command-xyz {image}")
        self.assertEqual(engine.extract("x.png"), "")


if __name__ == "__main__":
    unittest.main()
