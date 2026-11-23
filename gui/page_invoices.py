# -*- coding: utf-8 -*-
"""票据库页:筛选 + 表格(多选勾选)+ 编辑面板 + 勾选合计与汇总入口。"""
from __future__ import annotations

import os
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.archiver import archive, to_trash
from core.learned import learned_upsert
from gui.theme import btn
from core.models import (
    CATEGORIES,
    CATEGORY_UNKNOWN,
    STATUS_CONFIRMED,
)

PENDING_LABEL = "(待定)"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
FILETYPES = [(
    "票据", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif *.pdf"
), ("所有文件", "*.*")]


class InvoicesPage(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=app.theme["bg"])
        self.app = app
        app.attach_wallpaper(self)  # 壁纸底层,必须最先创建
        self._invoices: dict = {}
        self._photo = None
        self._build()

    # ---------- 构建 ----------
    def _build(self):
        t = self.app.theme
        self.configure(bg=t["bg"])

        from gui.theme import RoundedCard

        flt = RoundedCard(self, self.app, pad=10)
        flt.pack(fill="x", padx=18, pady=(16, 8))
        inner = flt.inner

        def lbl(text):
            tk.Label(inner, text=text, bg=t["card"],
                     fg=t["text_muted"]).pack(side="left")

        def spacer(w=8):
            tk.Frame(inner, bg=t["card"], width=w).pack(side="left")

        self.f_status = ttk.Combobox(
            inner, width=8, state="readonly",
            values=("全部状态", "待确认", "已确认"))
        self.f_status.current(0)
        self.f_category = ttk.Combobox(
            inner, width=12, state="readonly",
            values=("全部类别", *CATEGORIES))
        self.f_category.current(0)
        self.f_from = ttk.Entry(inner, width=11)
        self.f_to = ttk.Entry(inner, width=11)
        self.f_q = ttk.Entry(inner, width=14)

        lbl("状态"), self.f_status.pack(side="left"), spacer(8)
        lbl("类别"), self.f_category.pack(side="left"), spacer(8)
        lbl("日期"), self.f_from.pack(side="left")
        lbl("至"), self.f_to.pack(side="left", padx=(2, 8))
        lbl("搜索"), self.f_q.pack(side="left")
        btn(inner, "筛选", self.refresh, padx=12, pady=4).pack(
            side="left", padx=8)
        btn(inner, "＋ 添加票据", self.app.add_files, kind="primary",
            padx=12, pady=4).pack(side="right")
        btn(inner, "导入文件夹", self.app.add_folder, padx=12, pady=4).pack(
            side="right", padx=4)
        btn(inner, "重新识别待定", self.app._reimport, kind="ghost",
            padx=12, pady=4).pack(side="right", padx=4)
        for entry in (self.f_from, self.f_to, self.f_q):
            entry.bind("<Return>", lambda _e: self.refresh())

        columns = ("状态", "重复", "类别", "日期", "商户/行程", "金额",
                   "发票号")
        table = tk.Frame(self, bg=t["border"])
        table.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree = ttk.Treeview(table, columns=columns, show="tree headings",
                                 selectmode="extended")
        self.tree.heading("#0", text="编号")
        self.tree.column("#0", width=46, minwidth=46, stretch=False)
        for col, w in zip(columns, (70, 90, 110, 90, 260, 90, 130)):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="w")
        self.tree.tag_configure("pending", background=self.app.theme["pending_bg"])
        self.tree.tag_configure("dup", foreground=t["warn"])
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self._build_edit_panel()

        bar = tk.Frame(self, bg=t["bg"])
        bar.pack(fill="x", padx=12, pady=(4, 10))
        self.sel_var = tk.StringVar(value="未选择")
        tk.Label(bar, textvariable=self.sel_var, bg=t["bg"],
                 fg=t["text"]).pack(side="left")
        btn(bar, "导出 CSV", self._export_csv).pack(side="right")
        btn(bar, "生成汇总单 →", self._open_report, kind="primary").pack(
            side="right", padx=6)

    def _build_edit_panel(self):
        t = self.app.theme
        from gui.theme import RoundedCard

        panel = RoundedCard(self, self.app, pad=14)
        panel.pack(fill="x", padx=18, pady=(0, 6))
        head = tk.Frame(panel.inner, bg=panel.inner["bg"])
        head.pack(fill="x", pady=(0, 4))
        tk.Label(head, text="编辑面板(选中单条票据)", bg=head["bg"],
                 fg=t["text_muted"], font=("Microsoft YaHei", 9)).pack(
            side="left")

        body = tk.Frame(panel.inner, bg=panel.inner["bg"])
        body.pack(fill="x")
        self.preview = tk.Label(body, width=42, bg=t["card_soft"], fg=t["text_muted"],
                                text="(无预览)")
        self.preview.grid(row=0, column=0, rowspan=3, padx=(0, 10),
                          sticky="ns")

        fields = tk.Frame(body, bg=body["bg"])
        fields.grid(row=0, column=1, sticky="ew")
        body.columnconfigure(1, weight=1)

        self.e_category = self._field(fields, "类别", 0, 0, combo=True)
        self.e_amount = self._field(fields, "金额(元)", 0, 1)
        self.e_date = self._field(fields, "日期(YYYY-MM-DD)", 0, 2)
        self.e_merchant = self._field(fields, "商户/行程", 1, 0)
        self.e_no = self._field(fields, "发票号", 1, 1)
        self.e_note = self._field(fields, "备注", 1, 2)

        ops = tk.Frame(body, bg=t["card"])
        ops.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        btn(ops, "打开原图", self._open_image).pack(side="left")
        btn(ops, "✓ 确认归档", self._save_confirm, kind="primary").pack(
            side="left", padx=6)
        btn(ops, "保存", self._save_only).pack(side="left")
        self.b_keep = btn(ops, "强制保留", self._force_keep, kind="ghost")
        self.b_keep.config(state="disabled")
        self.b_keep.pack(side="left", padx=6)
        btn(ops, "删除(入回收站)", self._delete_selected,
            kind="danger").pack(side="right")

    def _field(self, parent, label: str, row: int, col: int,
               combo: bool = False):
        box = tk.Frame(parent, bg=parent["bg"])
        box.grid(row=row, column=col, padx=5, pady=3, sticky="ew")
        tk.Label(box, text=label, bg=parent["bg"],
                 fg=self.app.theme["text_muted"],
                 font=("Microsoft YaHei", 8)).pack(anchor="w")
        if combo:
            w = ttk.Combobox(box, state="readonly", width=18,
                             values=(PENDING_LABEL, *CATEGORIES))
        else:
            w = ttk.Entry(box, width=21)
        w.pack(fill="x")
        return w

    # ---------- 数据 ----------
    def filtered_rows(self):
        status = {"全部状态": None, "待确认": "pending",
                  "已确认": "confirmed"}[self.f_status.get()]
        category = self.f_category.get()
        return self.app.db.list_invoices(
            status=status,
            category=None if category == "全部类别" else category,
            date_from=self.f_from.get().strip() or None,
            date_to=self.f_to.get().strip() or None,
            q=self.f_q.get().strip() or None,
        )

    def refresh(self):
        rows = self.filtered_rows()
        t = self.app.theme
        self.tree.delete(*self.tree.get_children())
        self._invoices = {r.id: r for r in rows}
        for r in rows:
            values = (
                "已确认" if r.status == STATUS_CONFIRMED else "待确认",
                f"疑似#{r.dup_of}" if r.dup_flag else "",
                PENDING_LABEL if r.category == CATEGORY_UNKNOWN
                else r.category,
                r.invoice_date or "",
                r.merchant or "",
                f"{r.amount:.2f}" if r.amount is not None else "",
                r.invoice_no or "",
            )
            tags = []
            if r.status != STATUS_CONFIRMED:
                tags.append("pending")
            if r.dup_flag:
                tags.append("dup")
            self.tree.insert("", "end", iid=str(r.id), text=str(r.id),
                             values=values, tags=tags)
        self._update_summary()
        self._load_edit()

    def _picked(self) -> list[int]:
        return [int(iid) for iid in self.tree.selection()]

    def _update_summary(self):
        picked = [i for i in self._picked() if i in self._invoices]
        if not picked:
            self.sel_var.set("在表格中多选票据即完成勾选")
            return
        from decimal import Decimal

        total = sum((Decimal(str(self._invoices[i].amount))
                     for i in picked
                     if self._invoices[i].amount is not None),
                    Decimal("0"))
        self.sel_var.set(f"已选 {len(picked)} 张,合计 {total:.2f} 元")

    # ---------- 编辑面板 ----------
    def _on_select(self, _event=None):
        self._update_summary()
        self._load_edit()

    def _load_edit(self):
        picked = self._picked()
        if len(picked) != 1 or picked[0] not in self._invoices:
            self.app.editing_id = None
            self._set_preview(None)
            self.b_keep.config(state="disabled")
            return
        inv = self._invoices[picked[0]]
        self.app.editing_id = inv.id
        self.e_category.set(
            PENDING_LABEL if inv.category == CATEGORY_UNKNOWN
            else inv.category)
        for entry, value in (
            (self.e_amount, "" if inv.amount is None else f"{inv.amount:g}"),
            (self.e_date, inv.invoice_date or ""),
            (self.e_merchant, inv.merchant or ""),
            (self.e_no, inv.invoice_no or ""),
            (self.e_note, inv.note or ""),
        ):
            entry.delete(0, "end")
            entry.insert(0, value)
        self.b_keep.config(state="normal" if inv.dup_flag else "disabled")
        self._set_preview(inv)

    def _set_preview(self, inv):
        if inv is None:
            self._photo = None
            self.preview.config(image="", text="(无预览)")
            return
        if not self.app.has_pil:
            self._photo = None
            self.preview.config(
                image="", text="未安装 Pillow\n点「打开原图」查看")
            return
        path = next(
            (p for p in (inv.archived_path, inv.original_path)
             if p and Path(p).exists()), None)
        if not path:
            self._photo = None
            self.preview.config(image="", text="文件缺失")
            return
        try:
            if path.lower().endswith(".pdf"):
                from core import invoice_pdf

                img = invoice_pdf.render_page(path)
            else:
                from PIL import Image

                img = Image.open(path)
            img.thumbnail((300, 210))
            from PIL import ImageTk

            self._photo = ImageTk.PhotoImage(img)
            self.preview.config(image=self._photo, text="", width=300)
        except Exception:
            self._photo = None
            self.preview.config(image="", text="无法预览\n点「打开原图」查看")

    def _collect_fields(self) -> dict | None:
        category = self.e_category.get()
        category = CATEGORY_UNKNOWN if category == PENDING_LABEL else category
        amount_text = self.e_amount.get().strip()
        amount = None
        if amount_text:
            try:
                amount = float(amount_text)
            except ValueError:
                messagebox.showwarning("金额", "金额请填数字,如 358.00")
                return None
        date = self.e_date.get().strip()
        if date and not _DATE_RE.fullmatch(date):
            messagebox.showwarning("日期", "日期格式应为 YYYY-MM-DD")
            return None
        return {
            "category": category,
            "amount": amount,
            "invoice_date": date,
            "merchant": self.e_merchant.get().strip(),
            "invoice_no": self.e_no.get().strip(),
            "note": self.e_note.get().strip(),
        }

    def _apply_edit(self, confirm: bool):
        if self.app.editing_id is None:
            messagebox.showinfo("编辑", "请先在列表中选中一条票据")
            return
        fields = self._collect_fields()
        if fields is None:
            return
        inv = self.app.db.get_invoice(self.app.editing_id)
        if not inv:
            self.refresh()
            return
        for key, value in fields.items():
            setattr(inv, key, value)
        if confirm:
            inv.status = STATUS_CONFIRMED
        if inv.status == STATUS_CONFIRMED:
            if inv.category == CATEGORY_UNKNOWN:
                messagebox.showwarning("确认归档", "请先选择具体类别")
                return
            from core.archiver import archive

            archive(self.app.ws, inv, self.app.db)
            if inv.merchant:  # 学习闭环:人工确认沉淀商户→类别
                from core.learned import learned_upsert

                learned_upsert(self.app.db, inv.merchant, inv.category)
        self.app.db.update_invoice(inv)
        self.app.ws.log_action("edit", invoice_id=inv.id,
                               category=inv.category)
        self.refresh()

    def _save_confirm(self):
        self._apply_edit(confirm=True)

    def _save_only(self):
        self._apply_edit(confirm=False)

    def _force_keep(self):
        if self.app.editing_id is None:
            return
        inv = self.app.db.get_invoice(self.app.editing_id)
        if inv and inv.dup_flag:
            inv.dup_flag, inv.dup_of = 0, None
            self.app.db.update_invoice(inv)
            self.app.ws.log_action("force_keep", invoice_id=inv.id)
            self.refresh()

    def _delete_selected(self):
        picked = self._picked()
        if not picked:
            return
        if not messagebox.askyesno(
            "删除", f"删除选中的 {len(picked)} 张?\n索引删除,原图移入回收站。"
        ):
            return
        for iid in picked:
            inv = self._invoices.get(iid)
            if not inv:
                continue
            from core.archiver import to_trash

            to_trash(self.app.ws, inv, self.app.db)
            self.app.db.delete_invoice(inv.id)
            self.app.ws.log_action("delete", invoice_id=iid)
        self.refresh()

    def _open_image(self):
        if self.app.editing_id is None:
            return
        inv = self._invoices.get(self.app.editing_id)
        if not inv:
            return
        path = next(
            (p for p in (inv.archived_path, inv.original_path)
             if p and Path(p).exists()), None)
        if path and hasattr(os, "startfile"):
            os.startfile(path)  # noqa: S606
        else:
            messagebox.showinfo("打开原图", "文件缺失")

    # ---------- 汇总入口 ----------
    def _picked_invoices(self):
        ids = self._picked()
        if not ids:
            messagebox.showinfo("汇总", "请先在表格中多选票据")
            return []
        return self.app.db.invoices_by_ids(ids)

    def _open_report(self):
        invoices = self._picked_invoices()
        if invoices:
            from gui.report_dialog import ReportDialog

            ReportDialog(self, self.app.ws, self.app.db, invoices,
                         kind="docx")

    def _export_csv(self):
        invoices = self._picked_invoices()
        if invoices:
            from gui.report_dialog import ReportDialog

            ReportDialog(self, self.app.ws, self.app.db, invoices,
                         kind="csv")
