# -*- coding: utf-8 -*-
"""统计归纳:按类别合计与总额(给 GUI 统计面板用)。"""
from __future__ import annotations

from decimal import Decimal

from core.models import CATEGORY_UNKNOWN, Invoice


def _amount(inv: Invoice) -> Decimal:
    if inv.amount is None:
        return Decimal("0")
    return Decimal(str(inv.amount))


def category_totals(invoices: list[Invoice]) -> dict[str, Decimal]:
    """按类别合计金额;未确认类别显示为(待定);无金额计 0。"""
    totals: dict[str, Decimal] = {}
    for inv in invoices:
        label = "(待定)" if inv.category == CATEGORY_UNKNOWN \
            else inv.category
        totals[label] = totals.get(label, Decimal("0")) + _amount(inv)
    return totals


def total(invoices: list[Invoice]) -> Decimal:
    return sum((_amount(i) for i in invoices), Decimal("0"))
