# -*- coding: utf-8 -*-
"""SQLite 数据层:仅做票据索引,不存图片。

每方法内短事务;sqlite3.Row 转 dict 后交给 models.Invoice。
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from core.models import Invoice

_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT NOT NULL,
    archived_path TEXT,
    category      TEXT NOT NULL,
    amount        REAL,
    invoice_date  TEXT,
    merchant      TEXT,
    invoice_no    TEXT,
    reimburse_by  TEXT,
    project       TEXT,
    trip_reason   TEXT,
    note          TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    dup_flag      INTEGER NOT NULL DEFAULT 0,
    dup_of        INTEGER,
    file_hash     TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # ThreadingHTTPServer 多请求并发:同一连接必须串行使用,
        # 否则 pysqlite 事务状态交错会报 ProgrammingError
        self.lock = threading.RLock()

    def init_schema(self) -> None:
        with self.lock:
            with self.conn:
                self.conn.executescript(_SCHEMA)

    # ---- 票据 CRUD ----
    def insert_invoice(self, inv: Invoice) -> Invoice:
        with self.lock:
            if not inv.created_at:
                inv.created_at = datetime.now().isoformat(timespec="seconds")
            with self.conn:
                cur = self.conn.execute(
                    """INSERT INTO invoices
                       (original_path, archived_path, category, amount, invoice_date,
                        merchant, invoice_no, reimburse_by, project, trip_reason,
                        note, status, dup_flag, dup_of, file_hash, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (inv.original_path, inv.archived_path, inv.category, inv.amount,
                     inv.invoice_date or None, inv.merchant or None,
                     inv.invoice_no or None, inv.reimburse_by or None,
                     inv.project or None, inv.trip_reason or None,
                     inv.note or None, inv.status, inv.dup_flag, inv.dup_of,
                     inv.file_hash or None, inv.created_at),
                )
                inv.id = cur.lastrowid
            return inv

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
        return Invoice.from_row(dict(row)) if row else None

    def update_invoice(self, inv: Invoice) -> None:
        with self.lock:
            with self.conn:
                self.conn.execute(
                    """UPDATE invoices SET
                         original_path=?, archived_path=?, category=?, amount=?,
                         invoice_date=?, merchant=?, invoice_no=?, reimburse_by=?,
                         project=?, trip_reason=?, note=?, status=?, dup_flag=?,
                         dup_of=?, file_hash=?, created_at=?
                       WHERE id=?""",
                    (inv.original_path, inv.archived_path, inv.category, inv.amount,
                     inv.invoice_date or None, inv.merchant or None,
                     inv.invoice_no or None, inv.reimburse_by or None,
                     inv.project or None, inv.trip_reason or None,
                     inv.note or None, inv.status, inv.dup_flag, inv.dup_of,
                     inv.file_hash or None, inv.created_at, inv.id),
                )

    def delete_invoice(self, invoice_id: int) -> None:
        """只删索引记录;原图由调用方(archiver.to_trash)处理。"""
        with self.lock:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM invoices WHERE id = ?", (invoice_id,)
                )

    def list_invoices(self, status: str | None = None,
                      category: str | None = None,
                      date_from: str | None = None,
                      date_to: str | None = None,
                      q: str | None = None) -> list[Invoice]:
        """按条件筛选;日期含端点;q 模糊匹配商户/发票号/备注。"""
        sql = "SELECT * FROM invoices WHERE 1=1"
        args: list = []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if category:
            sql += " AND category = ?"
            args.append(category)
        if date_from:
            sql += " AND invoice_date >= ?"
            args.append(date_from)
        if date_to:
            sql += " AND invoice_date <= ?"
            args.append(date_to)
        if q:
            sql += """ AND (lower(merchant) LIKE ?
                          OR lower(invoice_no) LIKE ?
                          OR lower(note) LIKE ?)"""
            like = f"%{q.lower()}%"
            args += [like, like, like]
        sql += " ORDER BY invoice_date IS NULL, invoice_date, id"
        with self.lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [Invoice.from_row(dict(r)) for r in rows]

    def invoices_by_ids(self, ids: list[int]) -> list[Invoice]:
        """按传入顺序返回存在的记录。"""
        out: list[Invoice] = []
        for invoice_id in ids:
            inv = self.get_invoice(invoice_id)
            if inv:
                out.append(inv)
        return out

    # ---- 设置 ----
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.lock:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def close(self) -> None:
        self.conn.close()
