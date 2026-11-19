# -*- coding: utf-8 -*-
"""OCR 适配器测试:NoopOcr、CliOcr(成功/失败降级)、RapidOcr、引擎探测。"""
import unittest

import core.ocr as ocr_module
from core.db import Database
from core.ocr import CliOcr, NoopOcr, make_engine


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

    def test_image_path_quoted_against_shell_split(self):
        # 含 shell 元字符的路径必须整体加引号,不得拆成两条命令
        engine = CliOcr("cmd /c echo {image}")
        out = engine.extract("x & y.png")
        self.assertEqual(out.strip(), '"x & y.png"')

    def test_nonzero_exit_returns_empty(self):
        engine = CliOcr("cmd /c exit 1")
        self.assertEqual(engine.extract("x.png"), "")

    def test_missing_command_returns_empty(self):
        engine = CliOcr("definitely-not-a-command-xyz {image}")
        self.assertEqual(engine.extract("x.png"), "")


class TestMakeEngine(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path

        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.db = Database(str(self.td / "data.db"))
        self.db.init_schema()
        self.addCleanup(self.db.close)

    def test_explicit_cli_setting_wins(self):
        # 用户显式配置的命令优先级最高
        self.db.set_setting("ocr_cmd", "myocr {image}")
        self.assertIsInstance(make_engine(self.db), CliOcr)

    def test_falls_back_to_noop_when_nothing_available(self):
        original = ocr_module._rapid_available
        ocr_module._rapid_available = lambda: False
        self.addCleanup(setattr, ocr_module, "_rapid_available", original)
        self.assertIsInstance(make_engine(self.db), NoopOcr)

    def test_uses_rapid_when_available(self):
        original = ocr_module._rapid_available
        ocr_module._rapid_available = lambda: True
        self.addCleanup(setattr, ocr_module, "_rapid_available", original)
        self.assertIsInstance(make_engine(self.db), ocr_module.RapidOcr)


class TestRapidOcrReal(unittest.TestCase):
    """真实 RapidOCR 冒烟:未安装则跳过;任何异常都必须降级为空串。"""

    def test_blank_image_returns_empty_without_error(self):
        if not ocr_module._rapid_available():
            self.skipTest("rapidocr 未安装")
        import sys

        sys.path.insert(0, ".")
        from tests.util import make_png

        import tempfile
        from pathlib import Path

        f = Path(tempfile.mkdtemp()) / "blank.png"
        f.write_bytes(make_png())
        self.assertEqual(ocr_module.RapidOcr().extract(str(f)), "")

    def test_text_image_recognized(self):
        if not ocr_module._rapid_available():
            self.skipTest("rapidocr 未安装")
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            self.skipTest("Pillow 未安装")
        import tempfile
        from pathlib import Path

        f = Path(tempfile.mkdtemp()) / "text.png"
        img = Image.new("RGB", (400, 120), "white")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 64)
        draw.text((20, 30), "358.00", fill="black", font=font)
        img.save(f)
        text = ocr_module.RapidOcr().extract(str(f))
        self.assertIn("358", text)


if __name__ == "__main__":
    unittest.main()
