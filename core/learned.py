# -*- coding: utf-8 -*-
"""学习规则:用户确认的"商户→类别"沉淀下来,越用越准。

借鉴 auto-ontology 的 Learn 理念:人工确认是最高质量信号,
下次同类票据即使 OCR/文件名都没命中关键词,也能按学到的规则归类。
"""
from __future__ import annotations

import re

from core.db import Database

CONFIDENCE_LEARNED = 0.9  # 用户确认过,置信度高于关键词规则(0.7)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def learned_upsert(db: Database, merchant: str, category: str) -> None:
    """确认归档时沉淀:商户(去空白)→ 类别,冲突以最后一次确认为准。"""
    keyword = _norm(merchant)
    if not keyword or not category:
        return
    with db.lock:
        with db.conn:
            db.conn.execute(
                "INSERT INTO learned_rules(keyword, category, hits) "
                "VALUES (?, ?, 1) "
                "ON CONFLICT(keyword) DO UPDATE SET "
                "category = excluded.category, hits = hits + 1",
                (keyword, category),
            )


def learned_lookup(db: Database, squashed_text: str) -> tuple[str, float] | None:
    """文本(需已去空白)包含学到的商户名 → 返回 (类别, 0.9);命中多条取最 specific(最长关键词)。"""
    if not squashed_text:
        return None
    rows = db.conn.execute(
        "SELECT keyword, category, hits FROM learned_rules"
    ).fetchall()
    best = None
    for r in rows:
        if r["keyword"] and r["keyword"] in squashed_text:
            if best is None or len(r["keyword"]) > len(best["keyword"]):
                best = r
    if best is None:
        return None
    return best["category"], CONFIDENCE_LEARNED
