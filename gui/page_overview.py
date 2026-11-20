# -*- coding: utf-8 -*-
"""概览页:欢迎卡片、快捷导入入口、最近导入与快捷统计,支持自定义背景图。"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from core.summary import total

APP_DIR = Path(__file__).resolve().parent.parent


class OverviewPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._bg_photo = None
        self.configure(bg=self.app.theme["bg"])
        self.bind("<Configure>", lambda _e: self._draw())
        self._build()

    # ---------- 构建 ----------
    def _build(self):
        t = self.app.theme

        # 背景画布(自定义背景图时显示;无则纯色)
        self.canvas = tk.Canvas(self, bg=t["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        hero = tk.Frame(self.canvas, bg=t["card"], highlightthickness=1,
                        highlightbackground=t["border"])
        hero_win = self.canvas.create_window(60, 40, anchor="nw", window=hero)
        self._hero_win = hero_win

        tk.Label(hero, text="学生报销管家", bg=t["card"], fg=t["accent"],
                 font=("Microsoft YaHei", 10)).pack(anchor="w", padx=28,
                                                    pady=(24, 0))
        tk.Label(hero, text="票据归档,一键汇总。", bg=t["card"],
                 fg=t["text"], font=("Microsoft YaHei", 22, "bold")).pack(
            anchor="w", padx=28, pady=(6, 0))
        tk.Label(hero, text="导入票据照片或电子发票 PDF,自动识别内容并分类;"
                            "勾选票据一键生成正式报销汇总单。全部数据只存在本机。",
                 bg=t["card"], fg=t["text_muted"], justify="left",
                 font=("Microsoft YaHei", 10), wraplength=520).pack(
            anchor="w", padx=28, pady=8)

        btns = tk.Frame(hero, bg=t["card"])
        btns.pack(anchor="w", padx=28, pady=(4, 20))
        tk.Button(btns, text="导入票据图片(可多选)", bg=t["accent"],
                  fg="#ffffff", activebackground="#5a4bd4",
                  activeforeground="#ffffff", relief="flat",
                  font=("Microsoft YaHei", 10, "bold"), padx=16, pady=8,
                  cursor="hand2", command=self.app.add_files).pack(
            side="left")
        tk.Button(btns, text="导入文件夹", bg=t["card"], fg=t["accent"],
                  activebackground=t["accent_soft"], relief="flat",
                  font=("Microsoft YaHei", 10, "bold"), padx=16, pady=8,
                  cursor="hand2", command=self.app.add_folder).pack(
            side="left", padx=10)
        tk.Label(btns, text="也可以把文件直接拖进窗口", bg=t["card"],
                 fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(side="left", padx=6)

        # 快捷统计条
        self.stats_bar = tk.Frame(self.canvas, bg=t["card"],
                                  highlightthickness=1,
                                  highlightbackground=t["border"])
        self._stats_win = self.canvas.create_window(
            60, 300, anchor="nw", window=self.stats_bar)

        tip = tk.Label(self, text="提示:换背景图可在「设置」里选择你喜欢的图片;"
                                  "票据相关操作在左侧「票据库」。",
                       bg=t["bg"], fg=t["text_muted"],
                       font=("Microsoft YaHei", 9))
        self._tip_win = self.canvas.create_window(60, 420, anchor="nw",
                                                  window=tip)

    # ---------- 刷新 ----------
    def show(self):
        self._draw()
        self._refresh_stats()

    def _refresh_stats(self):
        t = self.app.theme
        for child in self.stats_bar.winfo_children():
            child.destroy()
        rows = self.app.db.list_invoices()
        pending = [r for r in rows if r.status != "confirmed"]
        chips = [
            ("票据总数", f"{len(rows)} 张"),
            ("待确认", f"{len(pending)} 张"),
            ("合计金额", f"{total(rows):.2f} 元"),
        ]
        tk.Label(self.stats_bar, text="当前工作区一览", bg=t["card"],
                 fg=t["text_muted"], font=("Microsoft YaHei", 9)).pack(
            anchor="w", padx=14, pady=(8, 0))
        row = tk.Frame(self.stats_bar, bg=t["card"])
        row.pack(padx=14, pady=(2, 12))
        for label, value in chips:
            chip = tk.Frame(row, bg=t["bg"])
            chip.pack(side="left", padx=(0, 14))
            tk.Label(chip, text=value, bg=t["bg"], fg=t["accent"],
                     font=("Microsoft YaHei", 16, "bold")).pack(anchor="w")
            tk.Label(chip, text=label, bg=t["bg"], fg=t["text_muted"],
                     font=("Microsoft YaHei", 9)).pack(anchor="w")

        recent = sorted(
            (r for r in rows if r.created_at),
            key=lambda r: r.created_at, reverse=True)[:5]
        tk.Label(self.stats_bar, text="最近导入", bg=t["card"],
                 fg=t["text_muted"], font=("Microsoft YaHei", 9)).pack(
            anchor="w", padx=14)
        if recent:
            for r in recent:
                amount = f"{r.amount:.2f} 元" if r.amount is not None else "金额未知"
                category = "(待定)" if r.category == "unknown" else r.category
                tk.Label(self.stats_bar,
                         text=f"  {r.created_at[:10]}  {category}  "
                              f"{r.merchant or '(未填商户)'}  {amount}",
                         bg=t["card"], fg=t["text"], anchor="w").pack(
                    fill="x", padx=14)
        else:
            tk.Label(self.stats_bar, text="  还没有票据,先点上面导入吧。",
                     bg=t["card"], fg=t["text_muted"], anchor="w").pack(
                fill="x", padx=14)

    def _draw(self):
        """铺背景:自定义图片(压暗)或纯主题色。"""
        t = self.app.theme
        w = max(self.canvas.winfo_width(), 800)
        h = max(self.canvas.winfo_height(), 560)
        self.canvas.coords(self._hero_win, 60, 40)
        self.canvas.coords(self._stats_win, 60, 330)
        self.canvas.coords(self._tip_win, 60, h - 60)
        bg_path = self.app.db.get_setting("background_image")
        photo = None
        if bg_path and Path(bg_path).exists() and self.app.has_pil:
            try:
                from PIL import Image, ImageTk

                img = Image.open(bg_path).convert("RGB")
                ratio = max(w / img.width, h / img.height)
                img = img.resize((int(img.width * ratio) + 1,
                                  int(img.height * ratio) + 1))
                # 压暗并淡化,保证前景可读
                white = Image.new("RGB", img.size, "#f4f5f7")
                img = Image.blend(img, white, 0.82)
                self._bg_photo = ImageTk.PhotoImage(img)
                self.canvas.create_image(0, 0, image=self._bg_photo,
                                         anchor="nw")
                photo = True
            except Exception:
                photo = None
        if not photo:
            self.canvas.create_rectangle(
                0, 0, w, h, fill=t["bg"], width=0)
