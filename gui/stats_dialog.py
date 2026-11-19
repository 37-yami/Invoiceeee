# -*- coding: utf-8 -*-
"""统计对话框:当前筛选结果的类别合计与总额。"""
from __future__ import annotations

import tkinter as tk

from core.models import CATEGORY_UNKNOWN, Invoice
from core.summary import category_totals, total


def _label(category: str) -> str:
    return "(待定)" if category == CATEGORY_UNKNOWN else category


class StatsDialog(tk.Toplevel):
    def __init__(self, parent, rows: list[Invoice]):
        super().__init__(parent)
        self.title("统计(当前筛选结果)")
        self.resizable(False, False)
        self.transient(parent)
        self.text = tk.Text(self, width=46, height=16,
                            font=("Consolas", 11))
        self.text.pack(padx=12, pady=12)
        self.text.insert("1.0", self._render(rows))
        self.text.config(state="disabled")

    @staticmethod
    def _render(rows: list[Invoice]) -> str:
        if not rows:
            return "当前筛选结果为空。"
        confirmed = [r for r in rows if r.status == "confirmed"]
        lines = [
            f"共 {len(rows)} 张,合计 {total(rows):.2f} 元",
            f"其中已确认 {len(confirmed)} 张,金额 {total(confirmed):.2f} 元",
            "-" * 32,
            "按类别:",
        ]
        for category, amount in sorted(category_totals(rows).items(),
                                       key=lambda kv: -kv[1]):
            count = sum(1 for r in rows
                        if _label(r.category) == category)
            lines.append(f"  {category}: {count} 张  {amount:.2f} 元")
        return "\n".join(lines)
