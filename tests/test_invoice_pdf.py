# -*- coding: utf-8 -*-
"""PDF 支持测试:文本抽取、渲染、导入管线(文本型免 OCR)。"""
import shutil
import tempfile
import unittest
from pathlib import Path

import fitz  # noqa: F401 - 环境应有 pymupdf

from core import invoice_pdf
from core.db import Database
from core.ocr import NoopOcr
from core.workspace import Workspace
from gui.importer import Importer

CJK = "china-s"  # PyMuPDF 内置中日韩字体


def make_text_pdf(path: Path, lines: list[str]) -> None:
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((60, 80 + i * 24), line, fontname=CJK, fontsize=11)
    doc.save(str(path))
    doc.close()


def make_blank_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


class TestInvoicePdf(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)

    def test_pdf_text_extracts_chinese(self):
        f = self.td / "a.pdf"
        make_text_pdf(f, ["价税合计:¥358.00",
                          "开票日期:2026年11月02日",
                          "发票号码:042001900111"])
        text = invoice_pdf.pdf_text(str(f))
        self.assertIn("358.00", text)
        self.assertIn("发票号码", text)

    def test_blank_pdf_empty_text(self):
        f = self.td / "b.pdf"
        make_blank_pdf(f)
        self.assertEqual(invoice_pdf.pdf_text(str(f)).strip(), "")

    def test_render_page_png(self):
        f = self.td / "c.pdf"
        make_text_pdf(f, ["hello"])
        out = self.td / "out.png"
        result = invoice_pdf.render_page_png(str(f), str(out))
        self.assertEqual(result, str(out))
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 100)

    def test_render_page_image(self):
        f = self.td / "d.pdf"
        make_text_pdf(f, ["hello"])
        img = invoice_pdf.render_page(str(f))
        self.assertGreaterEqual(img.width, 100)


class TestPdfImport(unittest.TestCase):
    """文本型 PDF 免 OCR 直接出字段;扫描型走文件名/OCR 回退。"""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.db = Database(str(self.ws.db_path))
        self.db.init_schema()
        self.addCleanup(self.db.close)

    def test_text_pdf_imports_with_fields_no_ocr(self):
        imp = Importer(self.ws, self.db, engine=NoopOcr())
        f = self.td / "酒店住宿发票.pdf"
        make_text_pdf(f, ["如家酒店住宿发票",
                          "价税合计:¥358.00",
                          "开票日期:2026年11月02日",
                          "发票号码:042001900111"])
        rows = imp.import_files([f])
        r = rows[0]
        self.assertEqual(r.category, "酒店住宿")
        self.assertEqual(r.status, "confirmed")
        self.assertEqual(r.amount, 358.0)
        self.assertEqual(r.invoice_date, "2026-11-02")
        self.assertEqual(r.invoice_no, "042001900111")
        self.assertTrue(Path(r.archived_path).exists())
        self.assertTrue(r.archived_path.endswith(".pdf"))

    def test_scanned_pdf_falls_back_to_filename(self):
        imp = Importer(self.ws, self.db, engine=NoopOcr())
        f = self.td / "高铁票12306.pdf"
        make_blank_pdf(f)
        rows = imp.import_files([f])
        self.assertEqual(rows[0].category, "高铁/铁路")
        self.assertEqual(rows[0].status, "pending")
        self.assertTrue(rows[0].archived_path.endswith(".pdf"))

    def test_scan_folder_includes_pdf(self):
        imp = Importer(self.ws, self.db)
        (self.td / "票").mkdir()
        make_text_pdf(self.td / "票" / "a.pdf", ["hi"])
        (self.td / "票" / "b.txt").write_bytes(b"x")
        found = imp.scan_folder(self.td / "票")
        self.assertEqual([p.name for p in found], ["a.pdf"])


if __name__ == "__main__":
    unittest.main()
