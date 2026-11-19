# -*- coding: utf-8 -*-
"""GUI 自动冒烟:不进 mainloop,程序化走完 导入→编辑→确认→勾选→生成 docx。

用法:python tools/smoke_gui.py
弹窗全部被替换为自动应答,窗口只短暂闪现,无需人工操作。
"""
import shutil
import sys
import tempfile
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 自动应答:冒烟不允许被弹窗阻塞(删除确认答"是",打开文件夹答"否")
messagebox.askyesno = lambda title, *a, **k: title == "删除"
messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: None

from core.db import Database  # noqa: E402
from core.ocr import NoopOcr  # noqa: E402
from core.workspace import Workspace  # noqa: E402
from gui.main_window import App  # noqa: E402
from gui.report_dialog import ReportDialog  # noqa: E402
from tests.util import make_png  # noqa: E402


def main() -> None:
    td = Path(tempfile.mkdtemp())
    ws = Workspace(td)
    ws.ensure()
    db = Database(str(ws.db_path))
    db.init_schema()

    app = App(ws, db)
    app.importer.engine = NoopOcr()  # 冒烟用空 OCR,快且确定
    app.update()

    # 1. 导入 3 张:两张带关键词文件名,一张中性
    src = td / "src"
    src.mkdir()
    files = []
    for name, color in (("高铁票12306.png", (1, 1, 1)),
                        ("酒店住宿发票.png", (2, 2, 2)),
                        ("photo.png", (3, 3, 3))):
        f = src / name
        f.write_bytes(make_png(color=color))
        files.append(f)
    rows = app.importer.import_files(files)
    assert len(rows) == 3, f"应导入 3 张,实际 {len(rows)}"
    app._refresh()
    app.update()
    assert len(app.tree.get_children()) == 3, "列表应有 3 行"
    print("导入与列表刷新:OK")

    # 2. 选中高铁票,填字段并确认归档
    rail = next(r for r in rows if r.category == "高铁/铁路")
    app.tree.selection_set(str(rail.id))
    app._load_edit()
    app.update()
    assert app.e_category.get() == "高铁/铁路", "编辑面板应带出类别"
    app.e_amount.delete(0, "end")
    app.e_amount.insert(0, "553.00")
    app.e_date.delete(0, "end")
    app.e_date.insert(0, "2026-11-01")
    app.e_merchant.delete(0, "end")
    app.e_merchant.insert(0, "12306 G1021")
    app._save_confirm()
    confirmed = db.get_invoice(rail.id)
    assert confirmed.status == "confirmed", "应已确认"
    assert Path(confirmed.archived_path).exists(), "归档文件应存在"
    print("编辑与确认归档:OK")

    # 3. 重复导入同一文件 → 标记
    dup_rows = app.importer.import_files([files[0]])
    assert dup_rows[0].dup_flag == 1, "重复上传应标记"
    print("重复检测:OK")

    # 4. 全选 → 合计 → 生成 docx 与 csv
    app._refresh()
    all_ids = list(app.tree.get_children())
    app.tree.selection_set(all_ids)
    app._update_summary()
    summary = app.sel_var.get()
    assert "已选 4 张" in summary, f"应选 4 张: {summary}"
    print("勾选合计:", summary)

    invoices = db.invoices_by_ids([int(i) for i in all_ids])
    dialog = ReportDialog(app, ws, db, invoices, kind="docx")
    dialog.e_name.insert(0, "冒烟测试")
    dialog.e_from.insert(0, "2026-11-01")
    dialog.e_to.insert(0, "2026-11-18")
    dialog._preview()
    assert "4 张" in dialog.preview_var.get()
    dialog._generate()
    docx_files = list(ws.exports_dir.glob("报销汇总单_冒烟测试_*.docx"))
    assert docx_files, "docx 应生成"
    print("docx 生成:OK →", docx_files[0].name)

    dialog2 = ReportDialog(app, ws, db, invoices, kind="csv")
    dialog2.e_name.insert(0, "冒烟测试")
    dialog2.e_from.insert(0, "2026-11-01")
    dialog2.e_to.insert(0, "2026-11-18")
    dialog2._generate()
    csv_files = list(ws.exports_dir.glob("报销明细_冒烟测试_*.csv"))
    assert csv_files, "csv 应生成"
    print("csv 生成:OK →", csv_files[0].name)

    # 5. 删除(入回收站)
    app.tree.selection_set(all_ids[:1])
    app._delete_selected()
    assert len(list(ws.trash_dir.iterdir())) >= 1, "回收站应有文件"
    print("删除入回收站:OK")

    app.destroy()
    db.close()
    shutil.rmtree(td)
    print("GUI 冒烟全部通过")


if __name__ == "__main__":
    main()
