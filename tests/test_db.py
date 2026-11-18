# -*- coding: utf-8 -*-
"""SQLite 数据层测试:CRUD、筛选、settings。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from core.db import Database
from core.models import Invoice


class DbTestCase(unittest.TestCase):
    """每个测试独立临时目录与数据库;清理顺序 LIFO:先关连接再删目录。"""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.td)
        self.db = Database(str(Path(self.td) / "data.db"))
        self.db.init_schema()
        self.addCleanup(self.db.close)


class TestInsertGet(DbTestCase):
    def test_insert_fills_id_and_created_at(self):
        inv = self.db.insert_invoice(
            Invoice(original_path="uploads/a.jpg", merchant="全季酒店")
        )
        self.assertIsNotNone(inv.id)
        self.assertNotEqual(inv.created_at, "")
        got = self.db.get_invoice(inv.id)
        self.assertEqual(got.merchant, "全季酒店")
        self.assertEqual(got.status, "pending")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.db.get_invoice(999))

    def test_init_schema_idempotent(self):
        self.db.init_schema()  # 再跑一次不报错


class TestListFilters(DbTestCase):
    def setUp(self):
        super().setUp()
        self.ids = []
        for kw in [
            dict(original_path="1.jpg", category="高铁/铁路",
                 invoice_date="2026-11-01", amount=553.0, merchant="12306",
                 invoice_no="E123456", status="confirmed"),
            dict(original_path="2.jpg", category="酒店住宿",
                 invoice_date="2026-11-02", amount=358.0, merchant="全季酒店",
                 invoice_no="042001900111", status="pending",
                 note="会议住宿"),
            dict(original_path="3.jpg", category="网约车",
                 invoice_date="2026-11-03", amount=45.0, merchant="滴滴出行",
                 status="confirmed"),
        ]:
            self.ids.append(self.db.insert_invoice(Invoice(**kw)).id)

    def test_filter_by_status(self):
        rows = self.db.list_invoices(status="confirmed")
        self.assertEqual({r.id for r in rows}, {self.ids[0], self.ids[2]})

    def test_filter_by_category(self):
        rows = self.db.list_invoices(category="酒店住宿")
        self.assertEqual([r.id for r in rows], [self.ids[1]])

    def test_filter_by_date_range_inclusive(self):
        # 含端点:11-01 至 11-02 应含两张
        rows = self.db.list_invoices(date_from="2026-11-01", date_to="2026-11-02")
        self.assertEqual({r.id for r in rows}, {self.ids[0], self.ids[1]})
        rows = self.db.list_invoices(date_from="2026-11-02")
        self.assertEqual({r.id for r in rows}, {self.ids[1], self.ids[2]})

    def test_filter_by_q_matches_merchant_invoice_no_note(self):
        self.assertEqual(len(self.db.list_invoices(q="全季")), 1)
        self.assertEqual(len(self.db.list_invoices(q="042001900111")), 1)
        self.assertEqual(len(self.db.list_invoices(q="会议住宿")), 1)
        self.assertEqual(len(self.db.list_invoices(q="不存在")), 0)

    def test_list_orders_by_date_then_id(self):
        rows = self.db.list_invoices()
        self.assertEqual([r.id for r in rows], self.ids)


class TestUpdateDelete(DbTestCase):
    def test_update_persists(self):
        inv = self.db.insert_invoice(Invoice(original_path="a.jpg"))
        inv.amount = 88.5
        inv.status = "confirmed"
        inv.merchant = "如家"
        self.db.update_invoice(inv)
        got = self.db.get_invoice(inv.id)
        self.assertEqual((got.amount, got.status, got.merchant),
                         (88.5, "confirmed", "如家"))

    def test_delete_removes_index_only(self):
        inv = self.db.insert_invoice(Invoice(original_path="a.jpg"))
        self.db.delete_invoice(inv.id)
        self.assertIsNone(self.db.get_invoice(inv.id))
        self.assertEqual(self.db.list_invoices(), [])

    def test_invoices_by_ids_keeps_input_order(self):
        a = self.db.insert_invoice(Invoice(original_path="a.jpg")).id
        b = self.db.insert_invoice(Invoice(original_path="b.jpg")).id
        c = self.db.insert_invoice(Invoice(original_path="c.jpg")).id
        rows = self.db.invoices_by_ids([c, a])
        self.assertEqual([r.id for r in rows], [c, a])


class TestSettings(DbTestCase):
    def test_set_get_roundtrip_and_default(self):
        self.assertIsNone(self.db.get_setting("default_name"))
        self.assertEqual(self.db.get_setting("default_name", "张三"), "张三")
        self.db.set_setting("default_name", "李四")
        self.assertEqual(self.db.get_setting("default_name"), "李四")
        self.db.set_setting("default_name", "王五")  # 覆盖
        self.assertEqual(self.db.get_setting("default_name"), "王五")


if __name__ == "__main__":
    unittest.main()
