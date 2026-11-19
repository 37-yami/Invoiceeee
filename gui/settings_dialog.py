# -*- coding: utf-8 -*-
"""设置对话框:默认报销人信息与可选 OCR 命令。"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.title("设置")
        self.resizable(False, False)
        frame = ttk.Frame(self)
        frame.pack(padx=14, pady=12)

        def field(label: str, key: str) -> ttk.Entry:
            box = ttk.Frame(frame)
            box.pack(fill="x", pady=3)
            ttk.Label(box, text=label, width=26, anchor="w",
                      justify="left").pack(side="left")
            entry = ttk.Entry(box, width=36)
            entry.insert(0, self.db.get_setting(key) or "")
            entry.pack(side="left", fill="x", expand=True)
            return entry

        self.e_name = field("默认报销人", "default_name")
        self.e_sid = field("默认学号/工号", "default_student_id")
        self.e_project = field("默认项目/课题组", "default_project")
        self.e_ocr = field(
            "OCR 命令(可选,含 {image};留空自动用 RapidOCR)",
            "ocr_cmd")

        ttk.Button(self, text="保存", command=self._save).pack(pady=(2, 12))

    def _save(self):
        for key, entry in (
            ("default_name", self.e_name),
            ("default_student_id", self.e_sid),
            ("default_project", self.e_project),
            ("ocr_cmd", self.e_ocr),
        ):
            self.db.set_setting(key, entry.get().strip())
        messagebox.showinfo("设置", "已保存", parent=self)
        self.destroy()
