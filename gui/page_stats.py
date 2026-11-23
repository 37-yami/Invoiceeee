# -*- coding: utf-8 -*-
"""统计页:当前筛选结果的类别合计与总额(内嵌页,不弹窗)。"""
from __future__ import annotations

import tkinter as tk

from core.models import CATEGORY_UNKNOWN, Invoice
from core.summary import category_totals, total


def _label(category: str) -> str:
    return "(待定)" if category == CATEGORY_UNKNOWN else category


def render_stats(rows: list[Invoice]) -> str:
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
        count = sum(1 for r in rows if _label(r.category) == category)
        lines.append(f"  {category}: {count} 张  {amount:.2f} 元")
    return "\n".join(lines)


class StatsPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.configure(bg=self.app.theme["bg"])
        head = tk.Frame(self, bg=self.app.theme["bg"])
        head.pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(head, text="统计(当前筛选结果)", bg=self.app.theme["bg"],
                 fg=self.app.theme["text"],
                 font=("Microsoft YaHei", 14, "bold")).pack(side="left")
        ttk_button = ttk_button = ttk_btn = None
        from gui.theme import btn

        btn(head, "刷新", self.show, padx=10, pady=4).pack(side="right")
        self.text = tk.Text(self, width=64, height=22,
                            font=("Consolas", 11), relief="flat",
                            background=self.app.theme["card"],
                            fg=self.app.theme["text"],
                            insertbackground=self.app.theme["text"],
                            padx=16, pady=12)
        self.text.pack(padx=12, pady=8, anchor="nw")

    def show(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert(
            "1.0", render_stats(self.app.pages["invoices"].filtered_rows()))
        self.text.config(state="disabled")
