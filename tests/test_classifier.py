# -*- coding: utf-8 -*-
"""分类器测试:关键词分类、金额/日期/发票号提取(含 Review Focus 边界)。"""
import unittest

from core.classifier import classify, extract_fields


class TestClassify(unittest.TestCase):
    CASES = [
        ("电子发票 行程单 滴滴出行", "网约车"),
        ("上海出租车发票 出租车费", "出租车/客运"),
        ("如家酒店住宿发票 住宿费", "酒店住宿"),
        ("中国东方航空 登机牌 机票", "机票"),
        ("12306 铁路客户服务中心 高铁车票", "高铁/铁路"),
        ("餐饮服务 餐厅结账单", "餐饮"),
    ]

    def test_each_category_matched_with_confidence(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                category, confidence = classify(text)
                self.assertEqual(category, expected)
                self.assertEqual(confidence, 0.7)

    def test_unrelated_text_is_unknown(self):
        category, confidence = classify("随便一句话,没有任何关键词")
        self.assertEqual(category, "unknown")
        self.assertEqual(confidence, 0.0)

    def test_empty_text_is_unknown(self):
        self.assertEqual(classify("")[0], "unknown")


class TestExtractFields(unittest.TestCase):
    def test_full_invoice_text(self):
        # Review Focus:千分位金额 + 中文日期 + 发票号
        text = ("电子发票(普通发票) 开票日期:2026年11月18日 "
                "销售方:如家酒店 价税合计(大写)壹仟元整 "
                "价税合计:¥1,234.50 发票号码:042001900111")
        fields = extract_fields(text)
        self.assertEqual(fields["amount"], 1234.5)
        self.assertEqual(fields["date"], "2026-11-18")
        self.assertEqual(fields["invoice_no"], "042001900111")

    def test_date_formats_normalized(self):
        # Review Focus:三种日期写法均归一化为 YYYY-MM-DD
        self.assertEqual(extract_fields("开票日期:2026/11/18")["date"],
                         "2026-11-18")
        self.assertEqual(extract_fields("开票日期:2026-11-18")["date"],
                         "2026-11-18")
        self.assertEqual(extract_fields("日期 2026年11月18日 出行")["date"],
                         "2026-11-18")

    def test_plain_amount_with_yuan(self):
        self.assertEqual(extract_fields("合计 553.00元")["amount"], 553.0)

    def test_text_without_fields_all_none(self):
        fields = extract_fields("没有任何可识别字段")
        self.assertIsNone(fields["amount"])
        self.assertIsNone(fields["date"])
        self.assertIsNone(fields["invoice_no"])

    def test_invoice_no_requires_digits(self):
        # 短号码不当作发票号
        self.assertIsNone(extract_fields("号码:123")["invoice_no"])

    def test_impossible_date_rejected(self):
        # 2月31日不存在 → 不产出日期,而不是带病入库
        self.assertIsNone(extract_fields("日期 2026年2月31日")["date"])
        # 无效日期后若还有合法日期,取合法的
        fields = extract_fields("2026年2月31日 与 2026-11-18 两天")
        self.assertEqual(fields["date"], "2026-11-18")


if __name__ == "__main__":
    unittest.main()
