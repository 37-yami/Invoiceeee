# -*- coding: utf-8 -*-
"""统计归纳测试:按类别合计、总额。"""
import unittest

from core.models import Invoice
from core.summary import category_totals, total


def inv(amount, category, status="confirmed"):
    return Invoice(id=1, original_path="x", amount=amount,
                   category=category, status=status)


class TestSummary(unittest.TestCase):
    def test_category_totals_groups_and_sums(self):
        rows = [
            inv(100.0, "餐饮"),
            inv(45.5, "餐饮"),
            inv(358.0, "酒店住宿"),
            inv(None, "网约车"),  # 未识别金额:计 0,但计入张数
            inv(88.0, "unknown"),  # 待定类别
        ]
        totals = category_totals(rows)
        self.assertEqual(totals["餐饮"], 145.5)
        self.assertEqual(totals["酒店住宿"], 358.0)
        self.assertEqual(totals["网约车"], 0)
        self.assertEqual(totals["(待定)"], 88.0)
        self.assertEqual(len(totals), 4)

    def test_total_uses_decimal_precision(self):
        rows = [inv(1234.5, "餐饮"), inv(88.0, "餐饮"), inv(0.01, "餐饮")]
        self.assertEqual(str(total(rows)), "1322.51")

    def test_empty(self):
        self.assertEqual(total([]), 0)
        self.assertEqual(category_totals([]), {})


if __name__ == "__main__":
    unittest.main()
