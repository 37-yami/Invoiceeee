# -*- coding: utf-8 -*-
"""概览页:欢迎卡片、导入入口、工作区一览与最近导入,支持自定义背景图。

背景图用底层 Label(place 铺满),内容卡片 pack 在上层——
不使用 Canvas,避免叠层顺序问题。
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from core.summary import total


class OverviewPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        t = app.theme
        self.configure(bg=t["bg"])
        self._bg_photo = None

        # 底层背景标签(自定义背景图时填充)
        self.bg_label = tk.Label(self, bg=t["bg"])
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        # 内容层
        content = tk.Frame(self, bg=t["bg"])
        content.place(x=0, y=0, relwidth=1, relheight=1)
        self.content = content
        content.columnconfigure(0, weight=1)

        # ---- 欢迎卡片 ----
        hero = tk.Frame(content, bg=t["card"], highlightthickness=1,
                        highlightbackground=t["border"])
        hero.grid(row=0, column=0, sticky="ew", padx=28, pady=(28, 14))
        tk.Label(hero, text="学生报销管家 · STUDENT REIMBURSE MANAGER",
                 bg=t["card"], fg=t["accent"], font=("Microsoft YaHei", 9)
                 ).pack(anchor="w", padx=32, pady=(26, 0))
        tk.Label(hero, text="票据归档,一键汇总。",
                 bg=t["card"], fg=t["text"],
                 font=("Microsoft YaHei", 24, "bold")).pack(
            anchor="w", padx=32, pady=(4, 0))
        tk.Label(hero,
                 text="导入票据照片或电子发票 PDF,自动识别内容并分类;"
                      "勾选票据一键生成正式报销汇总单。\n全部数据只存在本机。",
                 bg=t["card"], fg=t["text_muted"], justify="left",
                 font=("Microsoft YaHei", 10), wraplength=560).pack(
            anchor="w", padx=32, pady=(8, 14))

        from gui.theme import btn

        btns = tk.Frame(hero, bg=t["card"])
        btns.pack(anchor="w", padx=32, pady=(0, 26))
        btn(btns, "导入票据图片(可多选)", app.add_files,
            kind="primary", padx=18, pady=9).pack(side="left")
        btn(btns, "导入文件夹", app.add_folder,
            padx=18, pady=9).pack(side="left", padx=10)
        tk.Label(btns, text="也可以把文件直接拖进窗口  ⇱", bg=t["card"],
                 fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(side="left", padx=8)

        # ---- 数据一览 ----
        glance = tk.Frame(content, bg=t["card"], highlightthickness=1,
                          highlightbackground=t["border"])
        glance.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 10))
        self.glance = glance
        self._build_glance_header()

        # ---- 最近导入 ----
        recent = tk.Frame(content, bg=t["card"], highlightthickness=1,
                          highlightbackground=t["border"])
        recent.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 12))
        self.recent = recent

        tip = tk.Label(content,
                       text="小提示:左侧「票据库」筛选与勾选票据,"
                            "「设置」里可换工作区与背景图。",
                       bg=t["bg"], fg=t["text_muted"],
                       font=("Microsoft YaHei", 9))
        tip.grid(row=3, column=0, sticky="w", padx=30)

    def _build_glance_header(self):
        t = self.app.theme
        from gui.theme import btn

        head = tk.Frame(self.glance, bg=t["card"])
        head.pack(fill="x", padx=24, pady=(18, 8))
        tk.Label(head, text="工作区一览", bg=t["card"], fg=t["text"],
                 font=("Microsoft YaHei", 12, "bold")).pack(side="left")
        btn(head, "刷新", self.show, kind="ghost", padx=10,
            pady=4).pack(side="right")
        self.chips_row = tk.Frame(self.glance, bg=t["card"])
        self.chips_row.pack(fill="x", padx=24, pady=(0, 16))

    def show(self):
        self._refresh_glance()
        self._refresh_recent()
        self._draw_background()

    # ---------- 数据 ----------
    def _refresh_glance(self):
        t = self.app.theme
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
            chip = tk.Frame(self.chips_row, bg="#f7f8fb",
                            highlightthickness=1,
                            highlightbackground=t["border"])
            chip.pack(side="left", padx=(0, 12))
            tk.Label(chip, text=value, bg="#f7f8fb", fg=color,
                     font=("Microsoft YaHei", 17, "bold")).pack(
                anchor="w", padx=18, pady=(10, 0))
            tk.Label(chip, text=label,
                     bg="#f7f8fb", fg=t["text_muted"],
                     font=("Microsoft YaHei", 9)).pack(anchor="w", padx=18,
                                                       pady=(0, 10))

    def _refresh_recent(self):
        t = self.app.theme
        for child in self.recent.winfo_children():
            child.destroy()
        tk.Label(self.recent, text="最近导入", bg=t["card"], fg=t["text"],
                 font=("Microsoft YaHei", 12, "bold")).pack(
            anchor="w", padx=24, pady=(16, 6))
        rows = self.app.db.list_invoices()
        recent = sorted(
            (r for r in rows if r.created_at),
            key=lambda r: r.created_at, reverse=True)[:5]
        body = tk.Frame(self.recent, bg=t["card"])
        body.pack(fill="x", padx=24, pady=(0, 14))
        if not recent:
            tk.Label(body, text="还没有票据,点上面的按钮导入吧。",
                     bg=t["card"], fg=t["text_muted"],
                     font=("Microsoft YaHei", 10)).pack(anchor="w", pady=4)
            return
        for r in recent:
            line = tk.Frame(body, bg=t["card"])
            line.pack(fill="x", pady=2)
            amount = (f"{r.amount:.2f} 元"
                      if r.amount is not None else "金额未知")
            category = "(待定)" if r.category == "unknown" else r.category
            status = "已确认" if r.status == "confirmed" else "待确认"
            color = t["ok"] if r.status == "confirmed" else t["warn"]
            tk.Label(line, text=f"{r.invoice_date or r.created_at[:10]}",
                     bg=t["card"], fg=t["text_muted"], width=12,
                     anchor="w", font=("Microsoft YaHei", 9)).pack(side="left")
            tk.Label(line, text=f"{status} · {category}", bg=t["card"],
                     fg=color, width=18, anchor="w",
                     font=("Microsoft YaHei", 9)).pack(side="left")
            tk.Label(line, text=f"{r.merchant or '(未填商户)'}",
                     bg=t["card"], fg=t["text"], anchor="w",
                     font=("Microsoft YaHei", 10)).pack(
                side="left", padx=(0, 10))
            tk.Label(line, text=amount, bg=t["card"], fg=t["text"],
                     font=("Microsoft YaHei", 10, "bold")).pack(side="right")

    # ---------- 背景 ----------
    def _draw_background(self):
        t = self.app.theme
        bg_path = self.app.db.get_setting("background_image")
        if bg_path and Path(bg_path).exists() and self.app.has_pil:
            try:
                from PIL import Image, ImageTk

                img = Image.open(bg_path).convert("RGB")
                w = max(self.winfo_width(), 900)
                h = max(self.winfo_height(), 600)
                ratio = max(w / img.width, h / img.height)
                img = img.resize((int(img.width * ratio) + 1,
                                  int(img.height * ratio) + 1))
                overlay = Image.new("RGB", img.size, "#f7f8fc")
                img = Image.blend(img, overlay, 0.85)  # 压暗淡化保证可读
                self._bg_photo = ImageTk.PhotoImage(img)
                self.bg_label.config(image=self._bg_photo)
                return
            except Exception:
                pass
        self._bg_photo = None
        self.bg_label.config(image="", bg=t["bg"])
