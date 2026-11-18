# -*- coding: utf-8 -*-
"""重复检测:三层规则,归一化后完全一致,不做模糊匹配。

1. 文件哈希相同(同一文件重复上传)
2. 发票号相同(非空)
3. 日期 + 金额 + 商户归一化一致

命中返回疑似重复的对方 id;调用方标记 dup_flag/dup_of,用户可强制保留。
"""
from __future__ import annotations

from core.db import Database
from core.models import Invoice


def normalize(s: str | None) -> str:
    """去首尾与内部空白、转小写。"""
    return "".join((s or "").split()).lower()


def find_dup_of(db: Database, inv: Invoice) -> int | None:
    """返回疑似重复的最早记录 id;无则 None。排除自身。"""
    with db.lock:  # 与 Database 其他方法共用一把锁,避免并发交错
        conn = db.conn

        if inv.file_hash:
            row = conn.execute(
                "SELECT id FROM invoices WHERE file_hash = ? AND id != ? "
                "ORDER BY id LIMIT 1",
                (inv.file_hash, inv.id),
            ).fetchone()
            if row:
                return row["id"]

        if inv.invoice_no:
            row = conn.execute(
                "SELECT id FROM invoices WHERE invoice_no = ? AND id != ? "
                "AND invoice_no IS NOT NULL ORDER BY id LIMIT 1",
                (inv.invoice_no, inv.id),
            ).fetchone()
            if row:
                return row["id"]

        if inv.invoice_date and inv.amount is not None and inv.merchant:
            target = normalize(inv.merchant)
            rows = conn.execute(
                "SELECT id, merchant FROM invoices "
                "WHERE invoice_date = ? AND amount = ? AND merchant IS NOT NULL "
                "AND id != ? ORDER BY id",
                (inv.invoice_date, inv.amount, inv.id),
            ).fetchall()
            for r in rows:
                if normalize(r["merchant"]) == target:
                    return r["id"]

    return None
