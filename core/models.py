# -*- coding: utf-8 -*-
"""数据模型:票据类别、状态与 Invoice 记录。

字段与 SQLite invoices 表一一对应(spec),数据库是索引,原图在文件系统。
"""
from __future__ import annotations

from dataclasses import dataclass, fields

# 七类票据;unknown 是上传后未确认的初始类别,不在七类之内
CATEGORY_UNKNOWN = "unknown"
CATEGORIES: list[str] = [
    "高铁/铁路",
    "机票",
    "酒店住宿",
    "网约车",
    "出租车/客运",
    "餐饮",
    "其他",
]

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"

# to_dict 时 None 转 "" 的文本字段(便于前端与 JSON 使用)
_TEXT_FIELDS = (
    "archived_path",
    "invoice_date",
    "merchant",
    "invoice_no",
    "reimburse_by",
    "project",
    "trip_reason",
    "note",
    "file_hash",
    "created_at",
)


@dataclass
class Invoice:
    id: int | None = None
    original_path: str = ""
    archived_path: str | None = None
    category: str = CATEGORY_UNKNOWN
    amount: float | None = None
    invoice_date: str = ""  # YYYY-MM-DD;空串=未知
    merchant: str = ""
    invoice_no: str = ""
    reimburse_by: str = ""
    project: str = ""
    trip_reason: str = ""
    note: str = ""
    status: str = STATUS_PENDING
    dup_flag: int = 0
    dup_of: int | None = None
    file_hash: str = ""
    created_at: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "Invoice":
        """从 sqlite Row(dict)构造;未知键忽略。"""
        valid = {f.name for f in fields(cls)}
        return cls(**{k: row[k] for k in valid if k in row})

    def to_dict(self) -> dict:
        """给 JSON 用:文本字段 None → "",数值保持。"""
        d = self.__dict__.copy()
        for key in _TEXT_FIELDS:
            if d.get(key) is None:
                d[key] = ""
        return d
