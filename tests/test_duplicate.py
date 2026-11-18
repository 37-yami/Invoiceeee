# -*- coding: utf-8 -*-
"""重复检测测试:哈希、发票号、日期+金额+商户三层;排除自身。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from core.db import Database
from core.duplicate import find_dup_of, normalize
from core.models import Invoice


class DupTestCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.db = Database(str(self.td / "data.db"))
        self.db.init_schema()
        self.addCleanup(self.db.close)

    def add(self, **kw) -> Invoice:
        kw.setdefault("original_path", "uploads/x.jpg")
        return self.db.insert_invoice(Invoice(**kw))


class TestNormalize(unittest.TestCase):
    def test_normalize_strips_and_folds(self):
        self.assertEqual(normalize("  滴滴 出行 "), normalize("滴滴出行"))
        self.assertEqual(normalize("ABC"), normalize(" abc "))


class TestFindDupOf(DupTestCase):
    def test_same_file_hash(self):
        a = self.add(file_hash="h1")
        b = self.add(file_hash="h1", merchant="不同商户")
        self.assertEqual(find_dup_of(self.db, b), a.id)

    def test_same_invoice_no(self):
        a = self.add(invoice_no="042001900111", file_hash="h1")
        b = self.add(invoice_no="042001900111", file_hash="h2")
        self.assertEqual(find_dup_of(self.db, b), a.id)

    def test_same_date_amount_merchant(self):
        base = dict(invoice_date="2026-11-02", amount=358.0, merchant="全季酒店")
        a = self.add(file_hash="h1", **base)
        b = self.add(file_hash="h2", **base)
        self.assertEqual(find_dup_of(self.db, b), a.id)

    def test_normalized_merchant_counts_as_same(self):
        base = dict(invoice_date="2026-11-02", amount=358.0)
        a = self.add(merchant="全季 酒店", file_hash="h1", **base)
        b = self.add(merchant="全季酒店", file_hash="h2", **base)
        self.assertEqual(find_dup_of(self.db, b), a.id)

    def test_different_fields_no_dup(self):
        a = self.add(invoice_date="2026-11-02", amount=358.0, merchant="全季")
        b = self.add(invoice_date="2026-11-03", amount=358.0, merchant="全季")
        self.assertIsNone(find_dup_of(self.db, b))

    def test_not_self(self):
        a = self.add(file_hash="h1")
        self.assertIsNone(find_dup_of(self.db, a))

    def test_empty_optional_fields_no_false_positive(self):
        # 无哈希、无发票号、无日期金额的两条不算重复
        self.add()
        b = self.add()
        self.assertIsNone(find_dup_of(self.db, b))


if __name__ == "__main__":
    unittest.main()
