# -*- coding: utf-8 -*-
"""导入管线测试:多文件入库、自动分类、OCR 字段、重复、脏输入、格式、文件夹扫描。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from core.db import Database
from core.models import Invoice
from core.ocr import OcrEngine
from core.workspace import Workspace
from gui.importer import IMAGE_EXTS, Importer
from tests.util import make_png


class FakeEngine(OcrEngine):
    """注入用假 OCR:返回固定发票文本。"""

    def extract(self, image_path: str) -> str:
        return ("如家酒店住宿发票 住宿费 开票日期:2026年11月02日 "
                "价税合计:¥358.00 发票号码:042001900111")


class ImporterTestCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.db = Database(str(self.ws.db_path))
        self.db.init_schema()
        self.addCleanup(self.db.close)

    def source_file(self, name: str, content: bytes | None = None) -> Path:
        f = self.td / "src" / name
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(content if content is not None else make_png())
        return f


class TestImportFiles(ImporterTestCase):
    def test_neutral_images_stay_pending_in_uploads(self):
        # 空 OCR(Noop)+ 中性文件名 → unknown pending,原图留 uploads
        from core.ocr import NoopOcr

        imp = Importer(self.ws, self.db, engine=NoopOcr())
        rows = imp.import_files([
            self.source_file("a.png", make_png(color=(1, 1, 1))),
            self.source_file("b.png", make_png(color=(2, 2, 2))),
            self.source_file("c.png", make_png(color=(3, 3, 3))),
        ])
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r.status, "pending")
            self.assertEqual(r.category, "unknown")
            self.assertTrue(Path(r.original_path).exists())

    def test_filename_rule_classifies_and_archives(self):
        from core.ocr import NoopOcr

        imp = Importer(self.ws, self.db, engine=NoopOcr())
        rows = imp.import_files([self.source_file("高铁票12306.png")])
        self.assertEqual(rows[0].category, "高铁/铁路")
        self.assertEqual(rows[0].status, "pending")
        self.assertIn("高铁-铁路", rows[0].archived_path)

    def test_ocr_text_drives_fields_and_auto_confirm(self):
        # Review Focus:OCR 文本与文件名同时存在 → 内容优先,字段入库并自动确认
        imp = Importer(self.ws, self.db, engine=FakeEngine())
        rows = imp.import_files([self.source_file("a.png")])
        r = rows[0]
        self.assertEqual(r.category, "酒店住宿")
        self.assertEqual(r.status, "confirmed")
        self.assertEqual(r.amount, 358.0)
        self.assertEqual(r.invoice_date, "2026-11-02")
        self.assertEqual(r.invoice_no, "042001900111")
        self.assertTrue(Path(r.archived_path).exists())

    def test_reimport_same_content_flagged_duplicate(self):
        content = make_png(color=(9, 9, 9))
        imp = Importer(self.ws, self.db)
        first = imp.import_files([self.source_file("x.png", content)])
        second = imp.import_files([self.source_file("y.png", content)])
        self.assertEqual(second[0].dup_flag, 1)
        self.assertEqual(second[0].dup_of, first[0].id)

    def test_dirty_and_unsupported_skipped(self):
        from core.ocr import NoopOcr

        imp = Importer(self.ws, self.db, engine=NoopOcr())
        rows = imp.import_files([
            self.source_file("note.txt", b"hello"),
            self.source_file("empty.png", b""),
            self.source_file("good.png"),
        ])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].original_path.endswith(".png"))

    def test_extended_image_formats_accepted(self):
        # bmp/tiff/gif 等扩展格式一律可导入
        from core.ocr import NoopOcr

        imp = Importer(self.ws, self.db, engine=NoopOcr())
        rows = imp.import_files([
            self.source_file("scan.bmp"),
            self.source_file("receipt.tif"),
            self.source_file("anim.gif"),
        ])
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            sorted(Path(r.original_path).suffix for r in rows),
            [".bmp", ".gif", ".tif"],
        )
        self.assertEqual(
            IMAGE_EXTS,
            {".jpg", ".jpeg", ".png", ".webp",
             ".bmp", ".tif", ".tiff", ".gif"},
        )


class TestScanFolder(ImporterTestCase):
    def test_recursive_only_images_deduped(self):
        # Review Focus:子目录递归、非图片过滤、按绝对路径去重
        (self.td / "票" / "sub").mkdir(parents=True)
        (self.td / "票" / "1.png").write_bytes(make_png(color=(1, 1, 1)))
        (self.td / "票" / "sub" / "2.jpg").write_bytes(b"j")
        (self.td / "票" / "sub" / "3.pdf").write_bytes(b"p")
        (self.td / "票" / "说明.txt").write_bytes(b"t")
        imp = Importer(self.ws, self.db)
        found = imp.scan_folder(self.td / "票")
        self.assertEqual(
            sorted(p.name for p in found), ["1.png", "2.jpg"]
        )

    def test_missing_folder_returns_empty(self):
        imp = Importer(self.ws, self.db)
        self.assertEqual(imp.scan_folder(self.td / "不存在"), [])


class TestReimportUnknown(ImporterTestCase):
    def test_unknown_pending_reclassified(self):
        # 首次导入无 OCR(unknown),换引擎重识别后归类并归档
        from core.ocr import NoopOcr

        imp = Importer(self.ws, self.db, engine=NoopOcr())
        rows = imp.import_files([self.source_file("photo.png")])
        self.assertEqual(rows[0].category, "unknown")

        imp2 = Importer(self.ws, self.db, engine=FakeEngine())
        updated = imp2.reimport_unknown()
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].category, "酒店住宿")
        self.assertEqual(updated[0].status, "confirmed")


if __name__ == "__main__":
    unittest.main()
