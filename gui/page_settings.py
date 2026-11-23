# -*- coding: utf-8 -*-
"""设置页:默认报销人、OCR 命令、工作区切换、自定义背景图。"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gui.theme import btn


class SettingsPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        t = self.app.theme
        self.configure(bg=t["bg"])
        self.app.attach_wallpaper(self)  # 壁纸底层,必须最先创建

        from gui.theme import RoundedCard

        card = RoundedCard(self, self.app, pad=20)
        card.pack(fill="x", padx=18, pady=16)
        inner = card.inner

        self.e_ocr = self._field(
            inner, "OCR 命令(可选,留空自动用本地识别)", "ocr_cmd")

        sep = tk.Frame(inner, bg=t["border"], height=1)
        sep.pack(fill="x", pady=8)

        tk.Label(inner, text="Workspace(数据目录)", bg=inner["bg"], fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        wrow = tk.Frame(inner, bg=inner["bg"])
        wrow.pack(fill="x", pady=2)
        self.ws_var = tk.StringVar()
        tk.Label(wrow, textvariable=self.ws_var, bg=inner["bg"],
                 fg=t["text"], anchor="w").pack(side="left", fill="x",
                                                expand=True)
        btn(wrow, "打开文件夹", self._open_ws, padx=10, pady=4).pack(
            side="right")
        btn(wrow, "切换 Workspace…", self._switch_ws, kind="primary", padx=10,
            pady=4).pack(side="right", padx=6)

        sep2 = tk.Frame(inner, bg=t["border"], height=1)
        sep2.pack(fill="x", pady=8)

        tk.Label(inner, text="个性化", bg=inner["bg"], fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        brow = tk.Frame(inner, bg=inner["bg"])
        brow.pack(fill="x", pady=4)
        self.bg_var = tk.StringVar()
        tk.Label(brow, textvariable=self.bg_var, bg=inner["bg"],
                 fg=t["text"], anchor="w").pack(side="left", fill="x",
                                                expand=True)
        btn(brow, "清除背景", self._clear_bg, padx=10, pady=4).pack(
            side="right")
        btn(brow, "选择背景图片…", self._pick_bg, padx=10, pady=4).pack(
            side="right", padx=6)
        tk.Label(inner, text="背景铺满整个界面;分区清晰度取决于图片色系。",
                 bg=inner["bg"], fg=t["text_muted"],
                 font=("Microsoft YaHei", 8)).pack(anchor="w",
                                                   pady=(0, 8))

        btn(inner, "保存设置", self._save, kind="primary", padx=18,
            pady=7).pack(anchor="w", pady=(2, 4))
        self.msg = tk.Label(inner, text="", bg=inner["bg"], fg=t["ok"],
                            font=("Microsoft YaHei", 9))
        self.msg.pack(anchor="w", pady=(0, 4))

    def _field(self, parent, label: str, key: str) -> ttk.Entry:
        box = tk.Frame(parent, bg=parent["bg"])
        box.pack(fill="x", pady=3)
        tk.Label(box, text=label, bg=parent["bg"],
                 fg=self.app.theme["text_muted"],
                 font=("Microsoft YaHei", 9), anchor="w",
                 justify="left").pack(side="left", anchor="n", padx=(0, 8))
        entry = ttk.Entry(box, width=42)
        entry.setting_key = key
        entry.insert(0, self.app.db.get_setting(key) or "")
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def show(self):
        self.ws_var.set(str(self.app.ws.root))
        bg = self.app.db.get_setting("background_image") or ""
        self.bg_var.set(f"当前背景:自定义 {bg}" if bg
                        else "当前背景:内置默认壁纸")
        self.e_ocr.delete(0, "end")
        self.e_ocr.insert(0, self.app.db.get_setting("ocr_cmd") or "")

    def _save(self):
        self.app.db.set_setting("ocr_cmd", self.e_ocr.get().strip())
        self.app.reload_engine()
        self.msg.config(text="已保存")

    def _open_ws(self):
        from gui.report_dialog import open_folder

        open_folder(self.app.ws.root)

    def _switch_ws(self):
        folder = filedialog.askdirectory(title="选择(或新建)Workspace 文件夹")
        if not folder:
            return
        self.app.switch_workspace(folder)

    def _pick_bg(self):
        path = filedialog.askopenfilename(
            title="选择背景图片",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.bmp")],
        )
        if not path:
            return
        self.app.db.set_setting("background_image", path)
        self.bg_var.set(f"当前背景:{path}")
        self.app.refresh_background()
        self.msg.config(text="背景已更新,切到「概览」页查看效果")

    def _clear_bg(self):
        self.app.db.set_setting("background_image", "")
        self.bg_var.set("当前背景:内置默认壁纸")
        self.app.refresh_background()
        self.msg.config(text="背景已恢复内置默认壁纸")
