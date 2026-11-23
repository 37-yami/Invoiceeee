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
        t = app.theme
        self.configure(bg=t["bg"])
        self.app.attach_wallpaper(self)  # 壁纸底层,必须最先创建

        from gui.theme import RoundedCard, btn

        head = tk.Frame(self, bg=t["bg"])
        head.pack(fill="x", padx=22, pady=(18, 6))
        tk.Label(head, text="统计(当前筛选结果)", bg=t["bg"],
                 fg=t["text"],
                 font=("Microsoft YaHei", 14, "bold")).pack(side="left")
        btn(head, "刷新", self.show, padx=10, pady=4).pack(side="right")

        card = RoundedCard(self, app, pad=6)
        card.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        self.text = tk.Text(card.inner, font=("Consolas", 11),
                            relief="flat", bg=card.inner["bg"],
                            fg=t["text"], insertbackground=t["text"],
                            padx=16, pady=14, highlightthickness=0)
        self.text.pack(fill="both", expand=True)

    def show(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert(
            "1.0", render_stats(self.app.pages["invoices"].filtered_rows()))
        self.text.config(state="disabled")
