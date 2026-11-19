# -*- coding: utf-8 -*-
"""关键词分类与字段提取:规则可解释、可人工修正,OCR 只是增强。

分类优先级(先具体后宽泛):网约车 → 出租车/客运 → 酒店住宿 → 机票
→ 高铁/铁路 → 餐饮。命中任一关键词即返回该类别(置信度 0.7),
否则 unknown(0.0),由用户在待确认队列处理。
"""
from __future__ import annotations

import re
from datetime import date as _date

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
# 电子发票标配:（小写）后紧跟总价,是最可靠的金额来源
_AMOUNT_XIAOXIE = re.compile(
    r"(?:（小写）|\(小写\)|小写)[:：）]?\s*[¥￥]?"
    r"([0-9][0-9,]*(?:\.\d{1,2})?)")
_AMOUNT_CONTEXT_JIASHUI = "价税合计"
_AMOUNT_CONTEXT_HEJI = ("合计", "小写")
_AMOUNT_CONTEXT_JINE = "金额"

# 日期:三种写法归一化 YYYY-MM-DD
_DATE_PATTERNS = [
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
    re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"),
]

# 发票号:8–20 位数字
_INVOICE_NO = re.compile(r"(?:发票号码|发票号|号码)[:：]?\s*(\d{8,20})")


def _squash(text: str) -> str:
    """去掉全部空白:真实 PDF/OCR 文本常在字符间夹换行与空格。"""
    return re.sub(r"\s+", "", text)


def classify(text: str) -> tuple[str, float]:
    """按关键词组分类;原文与去空白文本都参与匹配。"""
    raw = text or ""
    norm = _squash(raw)
    for category, keywords in _RULES:
        for kw in keywords:
            if kw in raw or kw in norm:
                return category, CONFIDENCE_MATCH
    return CATEGORY_UNKNOWN, CONFIDENCE_NONE


def _parse_amount(raw: str, norm: str) -> float | None:
    """金额多级判定:（小写）> 价税合计语境 > 合计/金额语境 > 兜底最大值。

    税额常以"¥数字"出现且数值更小,不能仅靠"带语境取最大"。
    """
    for source in (raw, norm):
        m = _AMOUNT_XIAOXIE.search(source)
        if m:
            return float(m.group(1).replace(",", ""))

    candidates: list[tuple[float, int]] = []  # (数值, 语境层级 1-4)
    for regex in (_AMOUNT_CURRENCY, _AMOUNT_YUAN):
        for m in regex.finditer(raw):
            value = float(m.group(1).replace(",", ""))
            window = raw[max(0, m.start() - 12): m.start()]
            if _AMOUNT_CONTEXT_JIASHUI in window:
                tier = 1
            elif any(c in window for c in _AMOUNT_CONTEXT_HEJI):
                tier = 2
            elif _AMOUNT_CONTEXT_JINE in window:
                tier = 3
            else:
                tier = 4
            candidates.append((value, tier))
    if not candidates:
        return None
    for tier in (1, 2, 3):
        pool = [v for v, t in candidates if t == tier]
        if pool:
            return max(pool)
    return max(v for v, _ in candidates)


def _parse_date(text: str) -> str | None:
    for regex in _DATE_PATTERNS:
        for m in regex.finditer(text):
            y, mo, d = (int(g) for g in m.groups())
            try:  # 拒绝 2026-02-31 这类不存在的日期
                _date(y, mo, d)
            except ValueError:
                continue
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def extract_fields(text: str) -> dict:
    """从票据文本提取金额/日期/发票号;无则 None。

    原文匹配失败时,用去空白文本兜底(跨行/夹空格版式)。
    """
    raw = text or ""
    norm = _squash(raw)
    m = _INVOICE_NO.search(raw) or _INVOICE_NO.search(norm)
    return {
        "amount": _parse_amount(raw, norm),
        "date": _parse_date(raw) or _parse_date(norm),
        "invoice_no": m.group(1) if m else None,
    }
