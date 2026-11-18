# -*- coding: utf-8 -*-
"""关键词分类与字段提取:规则可解释、可人工修正,OCR 只是增强。

分类优先级(先具体后宽泛):网约车 → 出租车/客运 → 酒店住宿 → 机票
→ 高铁/铁路 → 餐饮。命中任一关键词即返回该类别(置信度 0.7),
否则 unknown(0.0),由用户在待确认队列处理。
"""
from __future__ import annotations

import re

from core.models import CATEGORY_UNKNOWN

# 每组关键词:命中其一即归该类;组间按列表顺序优先
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("网约车", ("滴滴", "行程单", "网约车", "T3出行", "曹操出行")),
    ("出租车/客运", ("出租车", "客运", "的士")),
    ("酒店住宿", ("酒店", "住宿", "宾馆")),
    ("机票", ("机票", "航空", "航班", "登机")),
    ("高铁/铁路", ("12306", "铁路", "高铁", "动车", "车次")),
    ("餐饮", ("餐饮", "餐厅", "饭店", "美食")),
]

CONFIDENCE_MATCH = 0.7
CONFIDENCE_NONE = 0.0

# 金额:¥/￥ 前缀 或 数字后接"元";支持千分位
_AMOUNT_CURRENCY = re.compile(r"[¥￥]\s*([0-9][0-9,]*(?:\.\d{1,2})?)")
_AMOUNT_YUAN = re.compile(r"([0-9][0-9,]*(?:\.\d{1,2})?)\s*元")
_AMOUNT_CONTEXT = ("价税合计", "合计", "金额")

# 日期:三种写法归一化 YYYY-MM-DD
_DATE_PATTERNS = [
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
    re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"),
]

# 发票号:8–20 位数字
_INVOICE_NO = re.compile(r"(?:发票号码|发票号|号码)[:：]?\s*(\d{8,20})")


def classify(text: str) -> tuple[str, float]:
    """按关键词组分类;返回 (类别, 置信度)。"""
    for category, keywords in _RULES:
        for kw in keywords:
            if kw in text:
                return category, CONFIDENCE_MATCH
    return CATEGORY_UNKNOWN, CONFIDENCE_NONE


def _parse_amount(text: str) -> float | None:
    """优先取"合计/金额"语境下的数,否则取最大值。"""
    matches: list[tuple[float, bool]] = []  # (数值, 是否有语境)
    for regex in (_AMOUNT_CURRENCY, _AMOUNT_YUAN):
        for m in regex.finditer(text):
            value = float(m.group(1).replace(",", ""))
            start = max(0, m.start() - 8)
            has_context = any(c in text[start:m.start()]
                              for c in _AMOUNT_CONTEXT)
            matches.append((value, has_context))
    if not matches:
        return None
    with_context = [v for v, c in matches if c]
    pool = with_context or [v for v, _ in matches]
    return max(pool)


def _parse_date(text: str) -> str | None:
    for regex in _DATE_PATTERNS:
        m = regex.search(text)
        if m:
            y, mo, d = (int(g) for g in m.groups())
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def extract_fields(text: str) -> dict:
    """从 OCR 文本提取金额/日期/发票号;无则 None。"""
    m = _INVOICE_NO.search(text)
    return {
        "amount": _parse_amount(text),
        "date": _parse_date(text),
        "invoice_no": m.group(1) if m else None,
    }
