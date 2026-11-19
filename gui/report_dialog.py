# -*- coding: utf-8 -*-
"""汇总单对话框:报销人信息 → 预览合计 → 生成 docx / CSV。"""
from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

from core import report_csv, report_docx
from core.db import Database
from core.models import Invoice
from core.workspace import Workspace


def open_folder(path: Path) -> None:
    """跨平台打开目录。"""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - 用户主动点击
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class ReportDialog(tk.Toplevel):
    def __init__(self, parent, ws: Workspace, db: Database,
                 invoices: list[Invoice], kind: str = "docx"):
        super().__init__(parent)
        self.ws = ws
        self.db = db
        self.invoices = invoices
        self.kind = kind
        self.title("生成报销汇总单" if kind == "docx" else "导出 CSV")
        self.resizable(False, False)
        self._build()
        self._preview()

    def _build(self):
        frame = ttk.Frame(self)
        frame.pack(padx=14, pady=12)

        def field(label: str, value: str, row: int, col: int) -> ttk.Entry:
            box = ttk.Frame(frame)
            box.grid(row=row, column=col, padx=6, pady=4, sticky="ew")
            ttk.Label(box, text=label).pack(anchor="w")
            entry = ttk.Entry(box, width=22)
            entry.insert(0, value)
            entry.pack(fill="x")
            return entry

        def setting(key: str) -> str:
            return self.db.get_setting(key) or ""

        self.e_name = field("报销人", setting("default_name"), 0, 0)
        self.e_sid = field("学号/工号", setting("default_student_id"), 0, 1)
        self.e_project = field("项目/课题组", setting("default_project"),
                               0, 2)
        self.e_from = field("出差起(YYYY-MM-DD)", "", 1, 0)
        self.e_to = field("出差止(YYYY-MM-DD)", "", 1, 1)
        self.e_reason = field("出差事由", "", 1, 2)

        self.preview_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.preview_var,
                  foreground="#2c6e49").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        ops = ttk.Frame(frame)
        ops.grid(row=3, column=0, columnspan=3, pady=(6, 0))
        ttk.Button(ops, text="预览合计", command=self._preview).pack(
            side="left")
        ttk.Button(ops,
                   text="生成 docx" if self.kind == "docx" else "导出 CSV",
                   command=self._generate).pack(side="left", padx=8)

    def _meta(self) -> dict:
        return {
            "name": self.e_name.get().strip(),
            "student_id": self.e_sid.get().strip(),
            "project": self.e_project.get().strip(),
            "date_from": self.e_from.get().strip(),
            "date_to": self.e_to.get().strip(),
            "reason": self.e_reason.get().strip(),
        }

    def _preview(self):
        total = sum(
            (Decimal(str(i.amount)) for i in self.invoices
             if i.amount is not None),
            Decimal("0"),
        )
        self.preview_var.set(
            f"共 {len(self.invoices)} 张,合计 {total:.2f} 元"
        )

    def _generate(self):
        meta = self._meta()
        try:
            if self.kind == "docx":
                out = report_docx.generate(self.ws, self.invoices, meta)
            else:
                out = report_csv.generate_csv(self.ws, self.invoices, meta)
        except Exception as e:
            messagebox.showerror("生成失败", str(e), parent=self)
            return
        self.ws.log_action("report", kind=self.kind,
                           count=len(self.invoices))
        if messagebox.askyesno(
            "完成", f"已生成:\n{out}\n\n打开导出文件夹?", parent=self,
        ):
            open_folder(out.parent)
        self.destroy()
