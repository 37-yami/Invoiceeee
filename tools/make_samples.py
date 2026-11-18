# -*- coding: utf-8 -*-
"""生成示例工作区与示例报销汇总单(纯本地、零网络)。

用法:python tools/make_samples.py
产物:
  samples/demo_workspace/          完整示例工作区(3 张已确认票据)
  samples/报销汇总单_示例同学_20261101-20261118.docx
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.archiver import archive
from core.classifier import classify
from core.db import Database
from core.models import Invoice, STATUS_CONFIRMED
from core.report_docx import generate
from core.workspace import Workspace
from tests.util import make_png

SAMPLES = [
    # (文件名, 日期, 金额, 商户/行程, 发票号)
    ("高铁票12306.png", "2026-11-01", 553.00, "12306 G1021 北京南-上海虹桥", "E123456789"),
    ("酒店住宿发票.png", "2026-11-02", 358.00, "全季酒店(上海虹桥店)", "042001900111"),
    ("滴滴出行行程单.png", "2026-11-03", 45.50, "滴滴出行 虹桥-会展中心", "DD2026110301"),
]

META = dict(name="示例同学", student_id="20261234", project="智能实验室课题组",
            date_from="2026-11-01", date_to="2026-11-18",
            reason="参加全国学术会议")


def main() -> None:
    samples_dir = ROOT / "samples"
    ws_dir = samples_dir / "demo_workspace"
    if ws_dir.exists():
        shutil.rmtree(ws_dir)
    ws = Workspace(ws_dir)
    ws.ensure()
    db = Database(str(ws.db_path))
    db.init_schema()
    db.set_setting("default_name", META["name"])
    db.set_setting("default_student_id", META["student_id"])
    db.set_setting("default_project", META["project"])

    invoices = []
    for filename, date, amount, merchant, invoice_no in SAMPLES:
        stem = Path(filename).stem
        category, _conf = classify(stem)  # 与上传管线同一条规则:文件名关键词
        f = ws.uploads_dir / filename
        f.write_bytes(make_png())
        inv = db.insert_invoice(Invoice(
            original_path=str(f), category=category,
            invoice_date=date, amount=amount, merchant=merchant,
            invoice_no=invoice_no, trip_reason=META["reason"],
            status=STATUS_CONFIRMED, reimburse_by=META["name"],
            project=META["project"],
        ))
        archive(ws, inv, db)
        invoices.append(inv)
        print(f"已归档:{filename} → {inv.archived_path}")

    out = generate(ws, invoices, META)
    dest = samples_dir / out.name
    shutil.copy(out, dest)
    print(f"示例汇总单:{dest}")
    print(f"示例工作区:{ws_dir}")


if __name__ == "__main__":
    main()
