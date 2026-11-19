# -*- coding: utf-8 -*-
"""PDF 电子发票支持:文本抽取、页面渲染(预览与 OCR 用)。

文本型 PDF(电子发票主流)直接抽取文字,无需 OCR;
扫描型 PDF 抽不出文字时,由调用方渲染成图后再走 OCR。
"""
from __future__ import annotations

from pathlib import Path

try:
    import pymupdf as _fitz  # PyMuPDF 新版模块名
except ImportError:  # 旧版仅提供 fitz
    import fitz as _fitz


def pdf_text(path: str) -> str:
    """拼接全部页面文本;损坏文件返回空串,不抛异常。"""
    try:
        with _fitz.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception:
        return ""


def render_page(path: str, dpi: int = 150):
    """渲染第一页为 PIL Image(GUI 预览用)。"""
    from PIL import Image
    import io

    with _fitz.open(path) as doc:
        pix = doc[0].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def render_page_png(path: str, out_path: str, dpi: int = 150) -> str:
    """渲染第一页为 PNG 文件(OCR 引擎按路径读图)。"""
    with _fitz.open(path) as doc:
        pix = doc[0].get_pixmap(dpi=dpi)
    pix.save(out_path)  # 按扩展名保存为 PNG
    return out_path
