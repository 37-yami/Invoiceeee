# -*- coding: utf-8 -*-
"""归档器测试:路径规则、安全化、移动、重归档、回收站。含 Review Focus 边界。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from core.archiver import archive, archive_path, sanitize_filename, to_trash
from core.db import Database
from core.models import Invoice
from core.workspace import Workspace


class ArchiverTestCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td)
        self.ws = Workspace(self.td)
        self.ws.ensure()
        self.db = Database(str(self.ws.db_path))
        self.db.init_schema()
        self.addCleanup(self.db.close)

    def make_uploaded(self, name: str = "a.jpg", content: bytes = b"x") -> Path:
        f = self.ws.uploads_dir / name
        f.write_bytes(content)
        return f


class TestSanitizeFilename(unittest.TestCase):
    def test_illegal_chars_removed(self):
        # Review Focus:Windows 非法字符
        self.assertEqual(sanitize_filename("北京/上海?酒店<>:*"), "北京上海酒店")

    def test_empty_and_blank_fallback(self):
        self.assertEqual(sanitize_filename(""), "未命名")
        self.assertEqual(sanitize_filename("   "), "未命名")

    def test_long_name_truncated(self):
        out = sanitize_filename("长" * 50, maxlen=30)
        self.assertLessEqual(len(out), 30)


class TestArchivePath(ArchiverTestCase):
    def test_path_rule_with_chinese_category(self):
        inv = Invoice(id=7, original_path="uploads/a.jpg",
                      category="高铁/铁路", invoice_date="2026-11-02",
                      merchant="12306", amount=553.0)
        p = archive_path(self.ws, inv)
        self.assertEqual(
            p.relative_to(self.ws.invoices_dir).as_posix(),
            "2026-11/高铁-铁路/20261102_12306_553.00_7.jpg",
        )

    def test_defaults_when_fields_missing(self):
        # 无日期(用 created_at)、无金额(0.00)、无商户(未命名)
        inv = Invoice(id=3, original_path="uploads/b.png",
                      category="餐饮", created_at="2026-11-18T09:00:00")
        p = archive_path(self.ws, inv)
        self.assertEqual(
            p.relative_to(self.ws.invoices_dir).as_posix(),
            "2026-11/餐饮/20261118_未命名_0.00_3.png",
        )


class TestArchive(ArchiverTestCase):
    def test_archive_moves_file_and_updates_db(self):
        f = self.make_uploaded("a.jpg")
        inv = self.db.insert_invoice(Invoice(
            original_path=str(f), category="餐饮",
            invoice_date="2026-11-02", merchant="小饭馆", amount=45.0))
        archived = archive(self.ws, inv, self.db)
        self.assertTrue(archived.exists())
        self.assertFalse(f.exists())  # 原位置已移走
        got = self.db.get_invoice(inv.id)
        self.assertEqual(Path(got.archived_path), archived)

    def test_rearchive_after_category_change_moves_file(self):
        f = self.make_uploaded("a.jpg")
        inv = self.db.insert_invoice(Invoice(
            original_path=str(f), category="餐饮",
            invoice_date="2026-11-02", merchant="小饭馆", amount=45.0))
        first = archive(self.ws, inv, self.db)
        inv.category = "酒店住宿"
        second = archive(self.ws, inv, self.db)
        self.assertFalse(first.exists())  # 旧归档文件消失
        self.assertTrue(second.exists())
        self.assertIn("酒店住宿", second.as_posix())

    def test_rearchive_unchanged_keeps_path(self):
        # 已归档票据字段未变时再次保存:路径不变,不追加 _1 后缀
        f = self.make_uploaded("a.jpg", b"data")
        inv = self.db.insert_invoice(Invoice(
            original_path=str(f), category="餐饮",
            invoice_date="2026-11-02", merchant="小饭馆", amount=45.0))
        first = archive(self.ws, inv, self.db)
        second = archive(self.ws, inv, self.db)
        self.assertEqual(first, second)
        self.assertTrue(second.exists())
        self.assertEqual(second.read_bytes(), b"data")

    def test_archive_conflict_appends_suffix(self):
        f = self.make_uploaded("a.jpg", b"new")
        inv = self.db.insert_invoice(Invoice(
            original_path=str(f), category="餐饮", invoice_date="2026-11-02",
            merchant="X", amount=1.0))
        # 预占目标路径(如从备份恢复出的旧文件)
        target = archive_path(self.ws, inv)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old")
        archived = archive(self.ws, inv, self.db)
        self.assertNotEqual(archived, target)
        self.assertTrue(target.exists())  # 旧文件未被覆盖
        self.assertEqual(archived.read_bytes(), b"new")
        self.assertEqual(archived.name, target.stem + "_1" + target.suffix)


class TestToTrash(ArchiverTestCase):
    def test_to_trash_moves_with_timestamp_prefix(self):
        f = self.make_uploaded("a.jpg")
        inv = self.db.insert_invoice(Invoice(
            original_path=str(f), category="餐饮",
            invoice_date="2026-11-02", merchant="X", amount=1.0))
        archived = archive(self.ws, inv, self.db)
        trash_path = to_trash(self.ws, inv, self.db)
        self.assertTrue(trash_path.exists())
        self.assertFalse(archived.exists())
        # 文件名含时间戳前缀与 id
        name = trash_path.name
        self.assertRegex(name, r"^\d{8}_\d{6}_\d+_")
        self.assertIn(".trash", str(trash_path))
        got = self.db.get_invoice(inv.id)
        self.assertIsNone(got.archived_path)  # 索引已清空归档路径


if __name__ == "__main__":
    unittest.main()
