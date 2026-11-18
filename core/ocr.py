# -*- coding: utf-8 -*-
"""可插拔 OCR:默认 NoopOcr,不引入重依赖;OCR 绝不阻塞核心流程。

CliOcr 允许配置外部本地 OCR 命令,模板中 {image} 为图片路径占位;
任何失败(命令不存在、非零退出、超时)都降级为空文本。
"""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod

_TIMEOUT_SECONDS = 30


class OcrEngine(ABC):
    @abstractmethod
    def extract(self, image_path: str) -> str:
        """返回图片文本;失败返回空串,不抛异常。"""


class NoopOcr(OcrEngine):
    """默认空实现:未配置 OCR 时使用,一切进待确认队列。"""

    def extract(self, image_path: str) -> str:
        return ""


class CliOcr(OcrEngine):
    """外部命令适配器,如 `tesseract {image} stdout -l chi_sim`。"""

    def __init__(self, cmd_template: str):
        self.cmd_template = cmd_template

    def extract(self, image_path: str) -> str:
        if "{image}" not in self.cmd_template:
            return ""
        # 整体加引号:防止文件名里的 &、空格等把命令拆开
        cmd = self.cmd_template.replace("{image}", f'"{image_path}"')
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        if proc.returncode != 0:
            return ""
        return proc.stdout.decode("utf-8", errors="replace").strip()
