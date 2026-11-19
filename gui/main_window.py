# -*- coding: utf-8 -*-
"""主窗口:工具栏 / 筛选 / 票据表格 / 编辑面板 / 状态栏。

- 表格多选即"勾选集",状态栏实时显示已选张数与合计
- 每个自动判断(类别/字段)都可在编辑面板人工修正
- 导入与 OCR 在后台线程跑,经 queue + after() 回主线程,不卡界面
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from core.archiver import archive, to_trash
from core.db import Database
from core.models import CATEGORIES, CATEGORY_UNKNOWN, STATUS_CONFIRMED
from core.workspace import Workspace
from gui.importer import Importer
from gui.report_dialog import ReportDialog
from gui.settings_dialog import SettingsDialog

CONFIG_PATH = Path.home() / ".student_invoice_gui.json"
PENDING_LABEL = "(待定)"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def _choose_workspace() -> Path | None:
    hidden = tk.Tk()
    hidden.withdraw()
    try:
        folder = filedialog.askdirectory(title="选择报销管家工作区(数据都存在这里)")
    finally:
        hidden.destroy()
    return Path(folder) if folder else None


def launch(workspace: str | None = None) -> None:
    """入口:参数 > 上次记忆 > 弹窗选择。"""
    ws_path = workspace or _load_config().get("workspace")
    if not ws_path or not Path(ws_path).exists():
        chosen = _choose_workspace()
        if not chosen:
            return
        ws_path = chosen
    ws = Workspace(Path(ws_path))
    ws.ensure()
    db = Database(str(ws.db_path))
    db.init_schema()
    _save_config({"workspace": str(ws.root.resolve())})
    app = App(ws, db)
    app.mainloop()
    db.close()


class App(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self, ws: Workspace, db: Database):
        super().__init__()
        self.ws = ws
        self.db = db
        self.importer = Importer(ws, db)
        self.queue: queue.Queue = queue.Queue()
        self._importing = False
        self._photo = None  # 防 PhotoImage 被回收
        self._selected: int | None = None
        self._invoices: dict = {}

        self.title("学生报销管家 · 本地运行,数据未离开本机")
        self.geometry("1150x700")
        self.report_callback_exception = self._report_callback_exception
        self._build_toolbar()
        self._build_filters()
        self._build_tree()
        self._build_edit_panel()
        self._build_status_bar()
        self._refresh()
        self.after(200, self._poll)
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    # ---------- UI 构建 ----------
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Button(bar, text="添加票据图片(可多选)",
                   command=self._add_files).pack(side="left")
        ttk.Button(bar, text="导入文件夹",
                   command=self._add_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="重新识别待定",
                   command=self._reimport).pack(side="left")
        ttk.Button(bar, text="打开工作区",
                   command=self._open_workspace).pack(side="left", padx=6)
        ttk.Button(bar, text="设置",
                   command=self._open_settings).pack(side="right")

    def _build_filters(self):
        flt = ttk.Frame(self)
        flt.pack(fill="x", padx=8, pady=2)
        self.f_status = ttk.Combobox(
            flt, width=8, state="readonly",
            values=("全部状态", "待确认", "已确认"))
        self.f_status.current(0)
        self.f_category = ttk.Combobox(
            flt, width=12, state="readonly",
            values=("全部类别", *CATEGORIES))
        self.f_category.current(0)
        self.f_from = ttk.Entry(flt, width=11)
        self.f_to = ttk.Entry(flt, width=11)
        self.f_q = ttk.Entry(flt, width=14)
        ttk.Label(flt, text="状态").pack(side="left")
        self.f_status.pack(side="left", padx=(2, 8))
        ttk.Label(flt, text="类别").pack(side="left")
        self.f_category.pack(side="left", padx=(2, 8))
        ttk.Label(flt, text="日期").pack(side="left")
        self.f_from.pack(side="left", padx=2)
        ttk.Label(flt, text="至").pack(side="left")
        self.f_to.pack(side="left", padx=(2, 8))
        ttk.Label(flt, text="搜索").pack(side="left")
        self.f_q.pack(side="left", padx=2)
        ttk.Button(flt, text="筛选", command=self._refresh).pack(side="left",
                                                                 padx=6)
        for entry in (self.f_from, self.f_to, self.f_q):
            entry.bind("<Return>", lambda _e: self._refresh())

    def _build_tree(self):
        columns = ("状态", "重复", "类别", "日期", "商户/行程", "金额",
                   "发票号")
        self.tree = ttk.Treeview(self, columns=columns, show="tree headings",
                                 selectmode="extended")
        self.tree.heading("#0", text="编号")
        self.tree.column("#0", width=50, stretch=False)
        widths = (70, 90, 110, 90, 260, 90, 130)
        for col, w in zip(columns, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(4, 2))
        self.tree.tag_configure("pending", background="#fff8e1")
        self.tree.tag_configure("dup", foreground="#b3541e")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _build_edit_panel(self):
        panel = ttk.LabelFrame(self, text="编辑(选中单条票据)")
        panel.pack(fill="x", padx=8, pady=2)

        self.preview = ttk.Label(panel, width=40, anchor="center")
        self.preview.grid(row=0, column=0, rowspan=3, padx=8, pady=8,
                          sticky="ns")

        fields = ttk.Frame(panel)
        fields.grid(row=0, column=1, sticky="ew")
        panel.columnconfigure(1, weight=1)

        def field(parent, label, row, col):
            box = ttk.Frame(parent)
            box.grid(row=row, column=col, padx=6, pady=3, sticky="ew")
            ttk.Label(box, text=label).pack(anchor="w")
            entry = ttk.Entry(box, width=22)
            entry.pack(fill="x")
            return entry

        box = ttk.Frame(fields)
        box.grid(row=0, column=0, padx=6, pady=3, sticky="ew")
        ttk.Label(box, text="类别").pack(anchor="w")
        self.e_category = ttk.Combobox(
            box, state="readonly", width=20,
            values=(PENDING_LABEL, *CATEGORIES))
        self.e_category.pack(fill="x")
        self.e_amount = field(fields, "金额(元)", 0, 1)
        self.e_date = field(fields, "日期(YYYY-MM-DD)", 0, 2)
        self.e_merchant = field(fields, "商户/行程", 1, 0)
        self.e_no = field(fields, "发票号", 1, 1)
        self.e_note = field(fields, "备注", 1, 2)

        ops = ttk.Frame(panel)
        ops.grid(row=2, column=1, sticky="ew", padx=6, pady=(4, 8))
        ttk.Button(ops, text="打开原图", command=self._open_image).pack(
            side="left")
        ttk.Button(ops, text="确认归档", command=self._save_confirm).pack(
            side="left", padx=6)
        ttk.Button(ops, text="保存", command=self._save_only).pack(side="left")
        self.b_keep = ttk.Button(ops, text="强制保留",
                                 command=self._force_keep, state="disabled")
        self.b_keep.pack(side="left", padx=6)
        ttk.Button(ops, text="删除(入回收站)",
                   command=self._delete_selected).pack(side="right")

    def _build_status_bar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", side="bottom", padx=8, pady=6)
        self.status_var = tk.StringVar(value=str(self.ws.root))
        ttk.Label(bar, textvariable=self.status_var, foreground="#666").pack(
            side="left")
        self.sel_var = tk.StringVar(value="未选择")
        ttk.Label(bar, textvariable=self.sel_var).pack(side="left", padx=16)
        ttk.Button(bar, text="导出 CSV",
                   command=self._export_csv).pack(side="right")
        ttk.Button(bar, text="生成汇总单",
                   command=self._open_report).pack(side="right", padx=6)

    # ---------- 全局异常兜底 ----------
    def _report_callback_exception(self, exc_type, exc_value, tb):
        """Tk 回调里的未捕获异常:弹窗 + 状态栏提示,不再静默。"""
        import traceback

        detail = "".join(
            traceback.format_exception(exc_type, exc_value, tb)
        )[-900:]
        self._status(f"出错了:{exc_value}")
        try:
            messagebox.showerror("出错了", detail, parent=self)
        except Exception:
            pass

    def _open_workspace(self):
        from gui.report_dialog import open_folder

        open_folder(self.ws.root)

    # ---------- 列表刷新 ----------
    def _refresh(self):
        status = {"全部状态": None, "待确认": "pending",
                  "已确认": "confirmed"}[self.f_status.get()]
        category = self.f_category.get()
        rows = self.db.list_invoices(
            status=status,
            category=None if category == "全部类别" else category,
            date_from=self.f_from.get().strip() or None,
            date_to=self.f_to.get().strip() or None,
            q=self.f_q.get().strip() or None,
        )
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
        total = sum(
            self._invoices[i].amount or 0
            for i in picked
        )
        self.sel_var.set(
            f"已选 {len(picked)} 张,合计 {total:.2f} 元"
            if picked else "未选择"
        )

    def _status(self, text: str) -> None:
        self.status_var.set(text)

    # ---------- 编辑面板 ----------
    def _on_select(self, _event=None):
        self._update_summary()
        self._load_edit()

    def _load_edit(self):
        picked = self._picked()
        if len(picked) != 1 or picked[0] not in self._invoices:
            self._selected = None
            self._set_preview(None)
            self.b_keep.config(state="disabled")
            return
        inv = self._invoices[picked[0]]
        self._selected = inv.id
        self.e_category.set(
            PENDING_LABEL if inv.category == CATEGORY_UNKNOWN
            else inv.category
        )
        for entry, value in (
            (self.e_amount, "" if inv.amount is None else f"{inv.amount:g}"),
            (self.e_date, inv.invoice_date or ""),
            (self.e_merchant, inv.merchant or ""),
            (self.e_no, inv.invoice_no or ""),
            (self.e_note, inv.note or ""),
        ):
            entry.delete(0, "end")
            entry.insert(0, value)
        self.b_keep.config(
            state="normal" if inv.dup_flag else "disabled")
        self._set_preview(inv)

    def _set_preview(self, inv):
        if inv is None:
            self._photo = None
            self.preview.config(image="", text="(无预览)")
            return
        if not HAS_PIL:
            self._photo = None
            self.preview.config(
                image="", text="未安装 Pillow\n点「打开原图」查看")
            return
        path = next(
            (p for p in (inv.archived_path, inv.original_path)
             if p and Path(p).exists()), None)
        if not path:
            self._photo = None
            self.preview.config(image="", text="图片文件缺失")
            return
        try:
            if path.lower().endswith(".pdf"):
                from core import invoice_pdf

                img = invoice_pdf.render_page(path)
            else:
                img = Image.open(path)
            img.thumbnail((300, 200))
            self._photo = ImageTk.PhotoImage(img)
            self.preview.config(image=self._photo, text="")
        except Exception:
            self._photo = None
            self.preview.config(image="", text="无法预览\n点「打开原图」查看")

    def _collect_fields(self) -> dict | None:
        """从编辑面板收集并校验;不合法弹提示返回 None。"""
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

    def _apply_edit(self, confirm: bool) -> None:
        if self._selected is None:
            messagebox.showinfo("编辑", "请先在列表中选中一条票据")
            return
        fields = self._collect_fields()
        if fields is None:
            return
        inv = self.db.get_invoice(self._selected)
        if not inv:
            self._refresh()
            return
        for key, value in fields.items():
            setattr(inv, key, value)
        if confirm:
            inv.status = STATUS_CONFIRMED
        if inv.status == STATUS_CONFIRMED:
            if inv.category == CATEGORY_UNKNOWN:
                messagebox.showwarning("确认归档", "请先选择具体类别")
                return
            archive(self.ws, inv, self.db)  # 确认或字段变更 → (重新)归档
        self.db.update_invoice(inv)
        self.ws.log_action("edit", invoice_id=inv.id, category=inv.category)
        self._refresh()

    def _save_confirm(self):
        self._apply_edit(confirm=True)

    def _save_only(self):
        self._apply_edit(confirm=False)

    def _force_keep(self):
        if self._selected is None:
            return
        inv = self.db.get_invoice(self._selected)
        if inv and inv.dup_flag:
            inv.dup_flag, inv.dup_of = 0, None
            self.db.update_invoice(inv)
            self.ws.log_action("force_keep", invoice_id=inv.id)
            self._refresh()

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
            to_trash(self.ws, inv, self.db)
            self.db.delete_invoice(inv.id)
            self.ws.log_action("delete", invoice_id=iid)
        self._refresh()

    def _open_image(self):
        if self._selected is None:
            return
        inv = self._invoices.get(self._selected)
        if not inv:
            return
        path = next(
            (p for p in (inv.archived_path, inv.original_path)
             if p and Path(p).exists()), None)
        if path and hasattr(os, "startfile"):
            os.startfile(path)
        else:
            messagebox.showinfo("打开原图", "图片文件缺失")

    # ---------- 导入 ----------
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择票据图片或 PDF(可多选)",
            filetypes=[(
                "票据", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"
                        " *.gif *.pdf"
            ), ("所有文件", "*.*")],
        )
        if paths:
            self._start_import([Path(p) for p in paths])

    def _add_folder(self):
        folder = filedialog.askdirectory(title="选择票据文件夹(递归导入)")
        if not folder:
            return
        files = self.importer.scan_folder(Path(folder))
        if not files:
            self._status("该文件夹没有图片文件")
            return
        self._start_import(files)

    def _on_drop(self, event):
        # 显式分支:目录递归导入,文件按扩展名校验
        files: list[Path] = []
        for raw in self.tk.splitlist(event.data):
            p = Path(raw)
            if p.is_dir():
                files.extend(self.importer.scan_folder(p))
            elif p.exists() and p.suffix.lower() in self.importer.ACCEPTED_EXTS:
                files.append(p)
        if files:
            self._start_import(files)

    def _reimport(self):
        if self._importing:
            return
        self._importing = True
        self._status("重新识别中……")

        def work():
            try:
                rows = self.importer.reimport_unknown()
            finally:
                self._importing = False
            self.queue.put(("reimported", rows))

        threading.Thread(target=work, daemon=True).start()

    def _start_import(self, paths):
        if self._importing:
            self._status("正在导入,请稍候……")
            return
        self._importing = True
        self._status(f"导入中(共 {len(paths)} 个文件,含 OCR 识别)……")

        def work():
            try:
                rows = self.importer.import_files(paths)
            finally:
                self._importing = False
            self.queue.put(("imported", rows))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, rows = self.queue.get_nowait()
                if kind == "imported":
                    dups = sum(1 for r in rows if r.dup_flag)
                    self._status(
                        f"已导入 {len(rows)} 张"
                        + (f",疑似重复 {dups} 张(可强制保留)" if dups else "")
                    )
                elif kind == "reimported":
                    self._status(f"重新识别 {len(rows)} 张")
                self._refresh()
        except queue.Empty:
            pass
        self.after(200, self._poll)

    # ---------- 汇总与设置 ----------
    def _picked_invoices(self):
        ids = self._picked()
        if not ids:
            messagebox.showinfo("汇总", "请先在列表中勾选票据(可多选)")
            return []
        return self.db.invoices_by_ids(ids)

    def _open_report(self):
        invoices = self._picked_invoices()
        if invoices:
            ReportDialog(self, self.ws, self.db, invoices, kind="docx")

    def _export_csv(self):
        invoices = self._picked_invoices()
        if invoices:
            ReportDialog(self, self.ws, self.db, invoices, kind="csv")

    def _open_settings(self):
        dialog = SettingsDialog(self, db=self.db)
        dialog.transient(self)
        dialog.grab_set()
        self.wait_window(dialog)
        if dialog.result:
            # 设置可能改了 OCR 命令 → 热重载引擎,无需重启
            self.importer = Importer(self.ws, self.db)
            self._status("设置已保存,OCR 引擎已按新配置加载")
