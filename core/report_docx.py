# -*- coding: utf-8 -*-
"""生成正式 .docx 报销汇总单(python-docx):正式、克制、可打印。"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

from core.archiver import sanitize_filename
from core.models import Invoice
from core.workspace import Workspace

FOOTER_NOTE = "由学生报销管家本地生成,数据未离开本机"
HEADER_ROW = ("序号", "日期", "类别", "事由/行程", "金额(元)", "票据编号", "备注")


def _money(value) -> str:
    return f"{Decimal(str(value)):.2f}" if value is not None else "0.00"


def _set_font(run, name="宋体", size=10.5, bold=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def _add_para(doc, text, size=10.5, bold=False,
              align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph()
    p.alignment = align
    _set_font(p.add_run(text), size=size, bold=bold)
    return p


def generate(ws: Workspace, invoices: list[Invoice], meta: dict) -> Path:
    """生成汇总单并返回文件路径;未选票据抛 ValueError。"""
    if not invoices:
        raise ValueError("未选择票据")

    doc = Document()
    _add_para(doc, "报销汇总单", size=16, bold=True,
              align=WD_ALIGN_PARAGRAPH.CENTER)

    date_from = meta.get("date_from", "")
    date_to = meta.get("date_to", "")
    info = (
        f"报销人:{meta.get('name', '')}    "
        f"学号/工号:{meta.get('student_id', '')}\n"
        f"项目/课题组:{meta.get('project', '')}    "
        f"附件张数:{len(invoices)} 张\n"
        f"出差起止:{date_from} 至 {date_to}    "
        f"出差事由:{meta.get('reason', '')}"
    )
    _add_para(doc, info)

    table = doc.add_table(rows=1, cols=len(HEADER_ROW))
    table.style = "Table Grid"
    for i, title in enumerate(HEADER_ROW):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(title)
        _set_font(run, bold=True)

    total = Decimal("0")
    for seq, inv in enumerate(invoices, start=1):
        row = table.add_row().cells
        values = (str(seq), inv.invoice_date or "", inv.category,
                  inv.merchant or "", _money(inv.amount),
                  inv.invoice_no or "", inv.note or "")
        for i, value in enumerate(values):
            row[i].text = ""
            run = row[i].paragraphs[0].add_run(value)
            _set_font(run)
            if i == 4:  # 金额右对齐
                row[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if inv.amount is not None:
            total += Decimal(str(inv.amount))

    sum_row = table.add_row().cells
    sum_row[3].text = ""
    _set_font(sum_row[3].paragraphs[0].add_run("合计"), bold=True)
    sum_row[4].text = ""
    run = sum_row[4].paragraphs[0].add_run(f"{total:.2f}")
    _set_font(run, bold=True)
    sum_row[4].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(footer.add_run(FOOTER_NOTE), size=9)

    filename = (f"报销汇总单_{sanitize_filename(meta.get('name', '未命名'))}_"
                f"{date_from.replace('-', '')}-{date_to.replace('-', '')}.docx")
    ws.exports_dir.mkdir(exist_ok=True)
    out = ws.exports_dir / filename
    doc.save(str(out))
    return out
