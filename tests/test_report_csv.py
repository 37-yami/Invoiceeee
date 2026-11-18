# -*- coding: utf-8 -*-
"""CSV 导出测试:utf-8-sig、表头与汇总单一致、合计行。"""
import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from core.models import Invoice
from core.report_csv import generate_csv
from core.workspace import Workspace


class TestGenerateCsv(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.invoices = [
            Invoice(id=1, original_path="1.jpg", category="高铁/铁路",
                    amount=1234.5, invoice_date="2026-11-01",
                    merchant="12306 G1", invoice_no="E000001"),
            Invoice(id=2, original_path="2.jpg", category="餐饮",
                    amount=88.0, invoice_date="2026-11-02",
                    merchant="食堂", invoice_no=""),
        ]

    def test_csv_utf8_sig_with_header_and_total(self):
        out = generate_csv(self.ws, self.invoices)
        self.assertTrue(out.exists())
        raw = out.read_bytes()
        self.assertEqual(raw[:3], b"\xef\xbb\xbf")  # Excel 可直接打开
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(text.splitlines()))
        self.assertEqual(rows[0], ["序号", "日期", "类别", "事由/行程",
                                   "金额(元)", "票据编号", "备注"])
        self.assertEqual(len(rows), 4)  # 表头 + 2 + 合计
        self.assertEqual(rows[1][0], "1")
        self.assertEqual(rows[1][4], "1234.50")
        self.assertEqual(rows[3][3], "合计")
        self.assertEqual(rows[3][4], "1322.50")

    def test_empty_invoices_raises(self):
        from core.report_csv import generate_csv as gc
        with self.assertRaises(ValueError):
            gc(self.ws, [])


if __name__ == "__main__":
    unittest.main()
