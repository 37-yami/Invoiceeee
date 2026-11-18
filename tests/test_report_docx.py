# -*- coding: utf-8 -*-
"""docx 汇总单测试:表格、合计、页脚、文件名、空选择拒绝。含 Review Focus。"""
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from docx import Document

from core.models import Invoice
from core.report_docx import FOOTER_NOTE, generate
from core.workspace import Workspace


def make_invoice(i: int, amount: float, **kw) -> Invoice:
    base = dict(
        id=i,
        original_path=f"uploads/{i}.jpg",
        category="高铁/铁路",
        amount=amount,
        invoice_date=f"2026-11-0{i}",
        merchant=f"12306 车次 G{i}",
        invoice_no=f"E{i:06d}",
        note="",
        status="confirmed",
    )
    base.update(kw)
    return Invoice(**base)


class TestGenerateDocx(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.meta = dict(name="张三", student_id="20261234",
                         project="课题组A", date_from="2026-11-01",
                         date_to="2026-11-18", reason="学术会议")

    def test_generate_creates_docx_with_table_sum_footer(self):
        invoices = [
            make_invoice(1, 1234.5),
            make_invoice(2, 88.00, category="酒店住宿", merchant="全季酒店"),
            make_invoice(3, 0.01, category="网约车", merchant="滴滴出行"),
        ]
        out = generate(self.ws, invoices, self.meta)
        self.assertTrue(out.exists())
        self.assertEqual(out.parent, self.ws.exports_dir)
        self.assertEqual(out.name,
                         "报销汇总单_张三_20261101-20261118.docx")

        doc = Document(str(out))
        texts = [p.text for p in doc.paragraphs if p.text.strip()]
        self.assertIn("报销汇总单", texts[0])
        self.assertTrue(any("张三" in t for t in texts))
        self.assertTrue(any("学术会议" in t for t in texts))
        self.assertTrue(any("3 张" in t for t in texts))  # 附件张数

        table = doc.tables[0]
        header = [c.text for c in table.rows[0].cells]
        self.assertEqual(header, ["序号", "日期", "类别", "事由/行程",
                                  "金额(元)", "票据编号", "备注"])
        self.assertEqual(len(table.rows), 5)  # 表头 + 3 行 + 合计
        row3 = [c.text for c in table.rows[3].cells]
        self.assertEqual(row3[0], "3")
        self.assertEqual(row3[4], "0.01")
        total = [c.text for c in table.rows[4].cells]
        # Review Focus:金额合计 1234.5 + 88.00 + 0.01 = 1322.51(Decimal)
        self.assertEqual(total[4], "1322.51")
        self.assertEqual(Decimal(total[4]),
                         Decimal("1234.5") + Decimal("88.00") + Decimal("0.01"))

        footer = doc.sections[0].footer.paragraphs[0].text
        self.assertIn(FOOTER_NOTE, footer)
        self.assertEqual(FOOTER_NOTE, "由学生报销管家本地生成,数据未离开本机")

    def test_empty_selection_raises(self):
        with self.assertRaises(ValueError):
            generate(self.ws, [], self.meta)


if __name__ == "__main__":
    unittest.main()
