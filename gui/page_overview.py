# -*- coding: utf-8 -*-
"""概览页:欢迎卡片、导入入口、工作区一览与最近导入。

壁纸与圆角卡片由主窗口统一管理:卡片为 RoundedCard,
圆角缺口透出壁纸,子元素全部放在 card.inner 里。
"""
from __future__ import annotations

import tkinter as tk

from core.summary import total
from gui.theme import RoundedCard, btn


class OverviewPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        t = app.theme
        self.configure(bg=t["bg"])

        # 壁纸底层(由主窗口统一管理,必须最先创建)
        app.attach_wallpaper(self)
        self.columnconfigure(0, weight=1)

        # ---- 欢迎卡片 ----
        hero = RoundedCard(self, app, pad=22)
        hero.grid(row=0, column=0, sticky="ew", padx=26, pady=(24, 12))
        import datetime

        hour = datetime.datetime.now().hour
        greet = ("早上好" if hour < 12
                 else "下午好" if hour < 18 else "晚上好")
        inner = hero.inner
        tk.Label(inner, text=f"{greet},票据归档,一键汇总。",
                 bg=inner["bg"], fg=t["text"],
                 font=("Microsoft YaHei", 24, "bold")).pack(
            anchor="w", pady=(4, 0))
        tk.Label(inner,
                 text="导入票据照片或 PDF,自动识别分类;勾选后一键生成报销汇总单。",
                 bg=inner["bg"], fg=t["text_muted"], justify="left",
                 font=("Microsoft YaHei", 10), wraplength=560).pack(
            anchor="w", pady=(8, 14))

        btns = tk.Frame(inner, bg=inner["bg"])
        btns.pack(anchor="w", pady=(0, 4))
        btn(btns, "导入票据图片(可多选)", app.add_files,
            kind="primary", padx=18, pady=9).pack(side="left")
        btn(btns, "导入文件夹", app.add_folder,
            padx=18, pady=9).pack(side="left", padx=10)
        tk.Label(btns, text="也可以把文件直接拖进窗口  ⇱", bg=inner["bg"],
                 fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(side="left", padx=8)

        # ---- 数据一览 ----
        glance = RoundedCard(self, app, pad=18)
        glance.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 10))
        self.glance = glance
        self._build_glance_header()

        # ---- 最近导入 ----
        recent = RoundedCard(self, app, pad=18)
        recent.grid(row=2, column=0, sticky="ew", padx=26, pady=(0, 10))
        self.recent = recent

    def _build_glance_header(self):
        t = self.app.theme
        inner = self.glance.inner

        head = tk.Frame(inner, bg=inner["bg"])
        head.pack(fill="x", pady=(2, 8))
        tk.Label(head, text="工作区一览", bg=inner["bg"], fg=t["text"],
                 font=("Microsoft YaHei", 12, "bold")).pack(side="left")
        btn(head, "刷新", self.show, kind="ghost", padx=10,
            pady=4).pack(side="right")
        self.chips_row = tk.Frame(inner, bg=inner["bg"])
        self.chips_row.pack(fill="x", pady=(0, 6))

    def show(self):
        self._refresh_glance()
        self._refresh_recent()

    # ---------- 数据 ----------
    def _refresh_glance(self):
        t = self.app.theme
        inner = self.glance.inner
        for child in self.chips_row.winfo_children():
            child.destroy()
        rows = self.app.db.list_invoices()
        pending = [r for r in rows if r.status != "confirmed"]
        chips = [
            ("票据总数", f"{len(rows)} 张", t["accent"]),
            ("待确认", f"{len(pending)} 张", t["warn"] if pending else t["ok"]),
            ("合计金额", f"{total(rows):.2f} 元", t["text"]),
        ]
        for label, value, color in chips:
            chip = tk.Frame(self.chips_row, bg=t["card_soft"])
            chip.pack(side="left", padx=(0, 12))
            tk.Label(chip, text=value, bg=t["card_soft"], fg=color,
                     font=("Microsoft YaHei", 17, "bold")).pack(
                anchor="w", padx=18, pady=(10, 0))
            tk.Label(chip, text=label,
                     bg=t["card_soft"], fg=t["text_muted"],
                     font=("Microsoft YaHei", 9)).pack(anchor="w", padx=18,
                                                       pady=(0, 10))

    def _refresh_recent(self):
        t = self.app.theme
        inner = self.recent.inner
        for child in inner.winfo_children():
            child.destroy()
        tk.Label(inner, text="最近导入", bg=inner["bg"], fg=t["text"],
                 font=("Microsoft YaHei", 12, "bold")).pack(
            anchor="w", pady=(2, 6))
        rows = self.app.db.list_invoices()
        recent = sorted(
            (r for r in rows if r.created_at),
            key=lambda r: r.created_at, reverse=True)[:5]
        body = tk.Frame(inner, bg=inner["bg"])
        body.pack(fill="x", pady=(0, 6))
        if not recent:
            tk.Label(body, text="还没有票据,点上面的按钮导入吧。",
                     bg=body["bg"], fg=t["text_muted"],
                     font=("Microsoft YaHei", 10)).pack(anchor="w", pady=4)
            return
        for r in recent:
            line = tk.Frame(body, bg=body["bg"])
            line.pack(fill="x", pady=2)
            amount = (f"{r.amount:.2f} 元"
                      if r.amount is not None else "金额未知")
            category = "(待定)" if r.category == "unknown" else r.category
            status = "已确认" if r.status == "confirmed" else "待确认"
            color = t["ok"] if r.status == "confirmed" else t["warn"]
            tk.Label(line, text=f"{r.invoice_date or r.created_at[:10]}",
                     bg=line["bg"], fg=t["text_muted"], width=12,
                     anchor="w", font=("Microsoft YaHei", 9)).pack(side="left")
            tk.Label(line, text=f"{status} · {category}", bg=line["bg"],
                     fg=color, width=18, anchor="w",
                     font=("Microsoft YaHei", 9)).pack(side="left")
            tk.Label(line, text=f"{r.merchant or '(未填商户)'}",
                     bg=line["bg"], fg=t["text"], anchor="w",
                     font=("Microsoft YaHei", 10)).pack(
                side="left", padx=(0, 10))
            tk.Label(line, text=amount, bg=line["bg"], fg=t["text"],
                     font=("Microsoft YaHei", 10, "bold")).pack(side="right")
