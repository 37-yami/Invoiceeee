# -*- coding: utf-8 -*-
"""设置页:默认报销人、OCR 命令、工作区切换、自定义背景图。"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


class SettingsPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        t = self.app.theme
        self.configure(bg=t["bg"])

        card = tk.Frame(self, bg=t["card"], highlightthickness=1,
                        highlightbackground=t["border"])
        card.pack(fill="x", padx=12, pady=12)
        inner = tk.Frame(card, bg=t["card"])
        inner.pack(padx=14, pady=10)

        tk.Label(inner, text="默认信息", bg=t["card"], fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        self.e_name = self._field(inner, "默认报销人", "default_name")
        self.e_sid = self._field(inner, "默认学号/工号", "default_student_id")
        self.e_project = self._field(inner, "默认项目/课题组",
                                     "default_project")
        self.e_ocr = self._field(
            inner, "OCR 命令(可选,含 {image};留空自动用 RapidOCR)",
            "ocr_cmd")

        sep = tk.Frame(card, bg=t["border"], height=1)
        sep.pack(fill="x", padx=14, pady=4)

        tk.Label(card, text="工作区", bg=t["card"], fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(anchor="w", padx=14)
        wrow = tk.Frame(card, bg=t["card"])
        wrow.pack(fill="x", padx=14, pady=2)
        self.ws_var = tk.StringVar()
        tk.Label(wrow, textvariable=self.ws_var, bg=t["card"],
                 fg=t["text"], anchor="w").pack(side="left", fill="x",
                                                expand=True)
        ttk.Button(wrow, text="打开文件夹",
                   command=self._open_ws).pack(side="right")
        ttk.Button(wrow, text="更换工作区…",
                   command=self._switch_ws).pack(side="right", padx=6)

        sep2 = tk.Frame(card, bg=t["border"], height=1)
        sep2.pack(fill="x", padx=14, pady=4)

        tk.Label(card, text="个性化", bg=t["card"], fg=t["text_muted"],
                 font=("Microsoft YaHei", 9)).pack(anchor="w", padx=14)
        brow = tk.Frame(card, bg=t["card"])
        brow.pack(fill="x", padx=14, pady=4)
        self.bg_var = tk.StringVar()
        tk.Label(brow, textvariable=self.bg_var, bg=t["card"],
                 fg=t["text"], anchor="w").pack(side="left", fill="x",
                                                expand=True)
        ttk.Button(brow, text="清除背景",
                   command=self._clear_bg).pack(side="right")
        ttk.Button(brow, text="选择背景图片…",
                   command=self._pick_bg).pack(side="right", padx=6)
        tk.Label(card, text="背景图会压暗淡化后铺在概览页,只在本机生效。",
                 bg=t["card"], fg=t["text_muted"],
                 font=("Microsoft YaHei", 8)).pack(anchor="w", padx=14,
                                                   pady=(0, 8))

        ttk.Button(card, text="保存设置", style="Accent.TButton",
                   command=self._save).pack(anchor="w", padx=14,
                                            pady=(2, 12))
        self.msg = tk.Label(card, text="", bg=t["card"], fg=t["ok"],
                            font=("Microsoft YaHei", 9))
        self.msg.pack(anchor="w", padx=14, pady=(0, 10))

    def _field(self, parent, label: str, key: str) -> ttk.Entry:
        box = tk.Frame(parent, bg=parent["bg"])
        box.pack(fill="x", pady=3)
        tk.Label(box, text=label, bg=parent["bg"],
                 fg=self.app.theme["text_muted"],
                 font=("Microsoft YaHei", 9), anchor="w",
                 justify="left").pack(side="left", anchor="n", padx=(0, 8))
        entry = ttk.Entry(box, width=42)
        entry.insert(0, self.app.db.get_setting(key) or "")
        entry.pack(side="left", fill="x", expand=True)
        return entry

    def show(self):
        self.ws_var.set(str(self.app.ws.root))
        bg = self.app.db.get_setting("background_image") or ""
        self.bg_var.set(f"当前背景:{bg}" if bg else "当前背景:默认(无图片)")

    def _save(self):
        for key, entry in (
            ("default_name", self.e_name),
            ("default_student_id", self.e_sid),
            ("default_project", self.e_project),
            ("ocr_cmd", self.e_ocr),
        ):
            self.app.db.set_setting(key, entry.get().strip())
        self.app.reload_engine()
        self.msg.config(text="已保存(OCR 引擎已按新配置加载)")

    def _open_ws(self):
        from gui.report_dialog import open_folder

        open_folder(self.app.ws.root)

    def _switch_ws(self):
        folder = filedialog.askdirectory(title="选择(或新建)工作区文件夹")
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
        self.bg_var.set("当前背景:默认(无图片)")
        self.app.refresh_background()
        self.msg.config(text="背景已恢复默认")
