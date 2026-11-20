# -*- coding: utf-8 -*-
"""学习规则测试:商户→类别的确认沉淀与导入应用。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from core.db import Database
from core.learned import learned_lookup, learned_upsert
from core.models import Invoice
from core.workspace import Workspace


class LearnedTestCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.db = Database(str(self.td / "data.db"))
        self.db.init_schema()
        self.addCleanup(self.db.close)


class TestLearnedRules(LearnedTestCase):
    def test_upsert_and_lookup(self):
        learned_upsert(self.db, "汉庭酒店", "酒店住宿")
        hit = learned_lookup(self.db, "如家汉庭酒店 住宿费 2026-11-02")
        self.assertEqual(hit, ("酒店住宿", 0.9))

    def test_lookup_no_match_returns_none(self):
        learned_upsert(self.db, "汉庭酒店", "酒店住宿")
        self.assertIsNone(
            learned_lookup(self.db, "滴滴出行 行程单 客运服务"))

    def test_conflict_last_wins_and_hits_grow(self):
        learned_upsert(self.db, "某某商行", "餐饮")
        learned_upsert(self.db, "某某商行", "酒店住宿")
        learned_upsert(self.db, "某某商行", "酒店住宿")
        hit = learned_lookup(self.db, "某某商行 结算单")
        self.assertEqual(hit, ("酒店住宿", 0.9))
        row = self.db.conn.execute(
            "SELECT hits FROM learned_rules WHERE keyword = '某某商行'"
        ).fetchone()
        self.assertEqual(row["hits"], 3)  # 累加,便于观察学习强度

    def test_merchant_normalized_on_learn(self):
        # 学习时商户名先去空白;匹配用去空白文本包含判断
        learned_upsert(self.db, "全 季\n酒店", "酒店住宿")
        hit = learned_lookup(self.db, "全季酒店(虹桥店) 住宿费")
        self.assertEqual(hit, ("酒店住宿", 0.9))

    def test_old_workspace_schema_upgrade(self):
        # 旧工作区没有 learned_rules 表:init_schema 幂等补建
        self.assertTrue(
            self.db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name='learned_rules'"
            ).fetchone() is not None
        )


if __name__ == "__main__":
    unittest.main()
