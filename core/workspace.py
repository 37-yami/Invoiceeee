# -*- coding: utf-8 -*-
"""工作区:目录结构、数据库路径与操作日志。

工作区可整体复制备份;所有数据(图、库、日志、导出)都在其内。
日志只记动作与元数据,不含 OCR 全文等敏感内容。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_SUBDIRS = ("invoices", "uploads", ".trash", "logs", "exports")


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)

    # ---- 目录与路径 ----
    @property
    def invoices_dir(self) -> Path:
        return self.root / "invoices"

    @property
    def uploads_dir(self) -> Path:
        return self.root / "uploads"

    @property
    def trash_dir(self) -> Path:
        return self.root / ".trash"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def db_path(self) -> Path:
        return self.root / "data.db"

    def ensure(self) -> None:
        """初始化工作区目录(幂等)。"""
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in _SUBDIRS:
            (self.root / sub).mkdir(exist_ok=True)

    # ---- 操作日志 ----
    def log_action(self, action: str, **meta) -> None:
        """向 logs/app.log 追加一行 JSON:时间 + 动作 + 元数据。

        按次开合文件而非常驻 handler:Windows 上常驻句柄会锁住日志文件,
        阻碍工作区目录的复制/删除备份;动作日志量极小,无性能顾虑。
        """
        self.logs_dir.mkdir(exist_ok=True)
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "meta": meta,
        }
        with open(self.logs_dir / "app.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
