# -*- coding: utf-8 -*-
"""测试助手:构造最小合法 PNG(纯 stdlib)。"""
import struct
import zlib


def make_png(width: int = 2, height: int = 2,
             color: tuple = (200, 30, 30)) -> bytes:
    """生成一个最小的真彩色 PNG 文件字节。"""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
