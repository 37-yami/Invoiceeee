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
        self._bg_job = None

        # 底层背景标签(自定义壁纸或内置默认壁纸)
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
        import datetime

        hour = datetime.datetime.now().hour
        greet = ("早上好" if hour < 12
                 else "下午好" if hour < 18 else "晚上好")
        tk.Label(hero, text=f"{greet},票据归档,一键汇总。",
                 bg=t["card"], fg=t["text"],
                 font=("Microsoft YaHei", 24, "bold")).pack(
            anchor="w", padx=32, pady=(26, 0))
        tk.Label(hero,
                 text="导入票据照片或 PDF,自动识别分类;勾选后一键生成报销汇总单。",
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

        # 窗口尺寸变化时防抖重绘壁纸
        self.bind("<Configure>", self._on_resize)

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
            chip = tk.Frame(self.chips_row, bg=t["card_soft"],
                            highlightthickness=1,
                            highlightbackground=t["border"])
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
    def _on_resize(self, _event):
        if self._bg_job:
            self.after_cancel(self._bg_job)
        self._bg_job = self.after(300, self._draw_background)

    def _bg_source(self) -> Path | None:
        """用户自定义背景优先,否则用内置默认壁纸。"""
        custom = self.app.db.get_setting("background_image")
        if custom and Path(custom).exists():
            return Path(custom)
        built_in = Path(__file__).resolve().parent.parent / "assets" \
            / "default_bg.png"
        if built_in.exists():
            return built_in
        return None

    def _draw_background(self):
        t = self.app.theme
        source = self._bg_source()
        if source and self.app.has_pil:
            try:
                from PIL import Image, ImageTk

                img = Image.open(source).convert("RGB")
                w = max(self.winfo_width(), 900)
                h = max(self.winfo_height(), 600)
                ratio = max(w / img.width, h / img.height)
                img = img.resize((int(img.width * ratio) + 1,
                                  int(img.height * ratio) + 1))
                overlay = Image.new("RGB", img.size, "#171923")
                img = Image.blend(img, overlay, 0.35)  # 压暗保证可读
                self._bg_photo = ImageTk.PhotoImage(img)
                self.bg_label.config(image=self._bg_photo)
                return
            except Exception:
                pass
        self._bg_photo = None
        self.bg_label.config(image="", bg=t["bg"])
