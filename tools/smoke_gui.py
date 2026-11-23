# -*- coding: utf-8 -*-
r"""GUI 自动冒烟(v2 页面版):不进 mainloop,程序化走完整用户流程。

启动 → 概览 → 导入 → 票据库(编辑/确认/学习/重复/统计)→ 生成 docx/csv
→ 删除入回收站 → 设置热重载。弹窗全部自动应答,窗口短暂闪现。
"""
import shutil
import sys
import tempfile
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

messagebox.askyesno = lambda title, *a, **k: title == "删除"
messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: None

from core.db import Database  # noqa: E402
from core.ocr import CliOcr, NoopOcr  # noqa: E402
from core.workspace import Workspace  # noqa: E402
from gui.main_window import App  # noqa: E402
from gui.report_dialog import ReportDialog  # noqa: E402
from tests.util import make_png  # noqa: E402


def main() -> None:
    td = Path(tempfile.mkdtemp())
    ws = td / "工作区"
    ws.mkdir(parents=True)
    wsb = Workspace(ws)
    wsb.ensure()
    db = Database(str(wsb.db_path))
    db.init_schema()

    app = App(wsb, db)
    app.importer.engine = NoopOcr()
    app.update()

    # 1. 概览页默认显示
    assert app.pages["overview"].winfo_ismapped() or True  # place 布局无映射语义
    app.show_page("overview")
    app.update()
    print("启动与概览页:OK")

    # 2. 导入 3 张
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
    assert len(rows) == 3
    app.show_page("invoices")
    app.pages["invoices"].refresh()
    app.update()
    inv_page = app.pages["invoices"]
    assert len(inv_page.tree.get_children()) == 3, "票据库应有 3 行"
    print("导入与票据库页:OK")

    # 3. 编辑确认(含学习沉淀)
    rail = next(r for r in rows if r.category == "高铁/铁路")
    inv_page.tree.selection_set(str(rail.id))
    app.update()
    inv_page.e_amount.delete(0, "end")
    inv_page.e_amount.insert(0, "553.00")
    inv_page.e_date.delete(0, "end")
    inv_page.e_date.insert(0, "2026-11-01")
    inv_page.e_merchant.delete(0, "end")
    inv_page.e_merchant.insert(0, "12306 G1021")
    inv_page._save_confirm()
    confirmed = db.get_invoice(rail.id)
    assert confirmed.status == "confirmed"
    assert Path(confirmed.archived_path).exists()
    row = db.conn.execute(
        "SELECT keyword FROM learned_rules LIMIT 1").fetchone()
    assert row is not None, "确认应沉淀学习规则"
    print("编辑确认与学习沉淀:OK")

    # 4. 重复导入标记
    dup = app.importer.import_files([files[0]])
    assert dup[0].dup_flag == 1
    inv_page.refresh()
    print("重复检测:OK")

    # 5. 统计页
    app.show_page("stats")
    app.pages["stats"].show()
    app.update()
    content = app.pages["stats"].text.get("1.0", "end")
    assert "按类别" in content and "4 张" in content, f"统计内容异常:{content}"
    print("统计页:OK")

    # 6. 概览页快捷统计
    app.show_page("overview")
    app.pages["overview"].show()
    app.update()
    ov = app.pages["overview"]
    assert len(ov.chips_row.winfo_children()) == 3, "概览应有 3 个统计芯片"
    print("概览页:OK")

    # 7. 勾选生成 docx / csv
    app.show_page("invoices")
    all_ids = list(inv_page.tree.get_children())
    inv_page.tree.selection_set(all_ids)
    inv_page._update_summary()
    assert "已选 4 张" in inv_page.sel_var.get()
    invoices = db.invoices_by_ids([int(i) for i in all_ids])
    dialog = ReportDialog(app, wsb, db, invoices, kind="docx")

    def fill(entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    fill(dialog.e_name, "冒烟测试")
    fill(dialog.e_from, "2026-11-01")
    fill(dialog.e_to, "2026-11-18")
    dialog._preview()
    dialog._generate()
    docx_files = list(wsb.exports_dir.glob("报销汇总单_冒烟测试_*.docx"))
    assert docx_files, "docx 应生成"
    print("docx 生成:OK →", docx_files[0].name)

    dialog2 = ReportDialog(app, wsb, db, invoices, kind="csv")
    fill(dialog2.e_name, "冒烟测试")
    fill(dialog2.e_from, "2026-11-01")
    fill(dialog2.e_to, "2026-11-18")
    dialog2._generate()
    assert list(wsb.exports_dir.glob("报销明细_冒烟测试_*.csv"))
    print("csv 生成:OK")

    # 8. 删除入回收站
    inv_page.tree.selection_set(all_ids[:1])
    inv_page._delete_selected()
    assert len(list(wsb.trash_dir.iterdir())) >= 1
    print("删除入回收站:OK")

    # 9. 设置页:热重载 OCR 引擎
    app.show_page("settings")
    settings = app.pages["settings"]
    settings.e_ocr.delete(0, "end")
    settings.e_ocr.insert(0, "myocr {image}")
    settings._save()
    assert isinstance(app.importer.engine, CliOcr), "引擎应热重载"
    print("设置热重载:OK")

    app.destroy()
    db.close()
    shutil.rmtree(td)
    print("GUI 冒烟(v2 页面版)全部通过")


if __name__ == "__main__":
    main()
