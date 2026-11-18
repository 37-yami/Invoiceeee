# -*- coding: utf-8 -*-
"""CSV 导出:字段与汇总单表格一致,utf-8-sig(Excel 直接打开不乱码)。"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from core.models import Invoice
from core.workspace import Workspace

COLUMNS = ("序号", "日期", "类别", "事由/行程", "金额(元)", "票据编号", "备注")


def _money(value) -> str:
    return f"{Decimal(str(value)):.2f}" if value is not None else "0.00"


def generate_csv(ws: Workspace, invoices: list[Invoice]) -> Path:
    if not invoices:
        raise ValueError("未选择票据")
    ws.exports_dir.mkdir(exist_ok=True)
    out = ws.exports_dir / "报销明细.csv"
    total = Decimal("0")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for seq, inv in enumerate(invoices, start=1):
            writer.writerow([
                seq, inv.invoice_date or "", inv.category,
                inv.merchant or "", _money(inv.amount),
                inv.invoice_no or "", inv.note or "",
            ])
            if inv.amount is not None:
                total += Decimal(str(inv.amount))
        writer.writerow(["", "", "", "合计", f"{total:.2f}", "", ""])
    return out
