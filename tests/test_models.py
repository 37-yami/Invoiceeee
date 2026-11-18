# -*- coding: utf-8 -*-
"""数据模型测试:Invoice 默认值、from_row/to_dict 往返。"""
import unittest

from core.models import (
    CATEGORIES,
    CATEGORY_UNKNOWN,
    STATUS_CONFIRMED,
    STATUS_PENDING,
    Invoice,
)


class TestCategoryEnums(unittest.TestCase):
    def test_seven_categories_and_unknown(self):
        self.assertEqual(len(CATEGORIES), 7)
        self.assertIn("高铁/铁路", CATEGORIES)
        self.assertIn("机票", CATEGORIES)
        self.assertIn("酒店住宿", CATEGORIES)
        self.assertIn("网约车", CATEGORIES)
        self.assertIn("出租车/客运", CATEGORIES)
        self.assertIn("餐饮", CATEGORIES)
        self.assertIn("其他", CATEGORIES)
        # unknown 不属于七类,是待确认初始态
        self.assertNotIn(CATEGORY_UNKNOWN, CATEGORIES)
        self.assertEqual(CATEGORY_UNKNOWN, "unknown")
        self.assertEqual(STATUS_PENDING, "pending")
        self.assertEqual(STATUS_CONFIRMED, "confirmed")


class TestInvoiceDefaults(unittest.TestCase):
    def test_defaults_for_new_record(self):
        inv = Invoice(original_path="uploads/a.jpg")
        self.assertIsNone(inv.id)
        self.assertIsNone(inv.archived_path)
        self.assertEqual(inv.category, CATEGORY_UNKNOWN)
        self.assertIsNone(inv.amount)
        self.assertEqual(inv.invoice_date, "")
        self.assertEqual(inv.status, STATUS_PENDING)
        self.assertEqual(inv.dup_flag, 0)
        self.assertIsNone(inv.dup_of)
        self.assertEqual(inv.created_at, "")


class TestRowRoundtrip(unittest.TestCase):
    def test_from_row_and_to_dict(self):
        row = {
            "id": 5,
            "original_path": "uploads/5.jpg",
            "archived_path": "invoices/2026-11/餐饮/20261102_某餐厅_45.00_5.jpg",
            "category": "餐饮",
            "amount": 45.0,
            "invoice_date": "2026-11-02",
            "merchant": "某餐厅",
            "invoice_no": "042001900111",
            "reimburse_by": "张三",
            "project": "课题组A",
            "trip_reason": "学术会议",
            "note": "",
            "status": "confirmed",
            "dup_flag": 0,
            "dup_of": None,
            "file_hash": "abc123",
            "created_at": "2026-11-18T10:00:00",
        }
        inv = Invoice.from_row(row)
        self.assertEqual(inv.id, 5)
        self.assertEqual(inv.merchant, "某餐厅")
        d = inv.to_dict()
        for key, value in row.items():
            self.assertEqual(d[key], value, f"字段 {key} 往返不一致")

    def test_to_dict_converts_none_text_to_empty(self):
        # JSON 序列化时文本空值(None)转 "",避免前端 null
        inv = Invoice(
            id=1,
            original_path="uploads/x.jpg",
            archived_path=None,
            invoice_date=None,
            merchant=None,
            dup_of=None,
        )
        d = inv.to_dict()
        self.assertEqual(d["archived_path"], "")
        self.assertEqual(d["invoice_date"], "")
        self.assertEqual(d["merchant"], "")
        self.assertIsNone(d["dup_of"])
        self.assertIsNone(d["amount"])


if __name__ == "__main__":
    unittest.main()
