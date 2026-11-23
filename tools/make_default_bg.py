# -*- coding: utf-8 -*-
"""生成默认背景壁纸(纯 PIL,离端到端可控):深紫渐变 + 柔光斑。

用法:python tools/make_default_bg.py
输出:assets/default_bg.png(1920x1200)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parent.parent
W, H = 1920, 1200


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main() -> None:
    # 1. 对角渐变:深蓝黑 → 深紫
    top = (18, 19, 30)      # #12131e
    bottom = (42, 35, 80)   # #2a2350
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = (y / H) ** 1.2
        # 水平再轻微偏移,形成对角感
        for x in range(0, W, 4):
            tt = min(1.0, t + (x / W) * 0.12)
            c = lerp(top, bottom, tt)
            for dx in range(4):
                if x + dx < W:
                    px[x + dx, y] = c

    # 2. 柔光斑(高斯模糊的彩色椭圆,营造氛围)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    spots = [
        (300, 260, 520, (86, 70, 190)),    # 紫
        (1560, 320, 640, (60, 90, 200)),   # 蓝
        (960, 1000, 760, (120, 60, 170)),  # 深紫
        (1700, 950, 420, (70, 60, 160)),
        (120, 900, 380, (50, 80, 170)),
    ]
    for cx, cy, r, color in spots:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    img = Image.blend(img, Image.blend(img, glow, 0.55), 0.85)

    # 3. 细微曲线光带
    band = Image.new("RGB", (W, H), (0, 0, 0))
    d2 = ImageDraw.Draw(band)
    for i in range(3):
        offset = i * 130
        points = []
        import math

        for x in range(0, W + 10, 10):
            y = (H * 0.42 + offset
                 + 140 * math.sin(x / 520 + i * 1.4)
                 + 60 * math.sin(x / 210 + i))
            points.append((x, y))
        d2.line(points, fill=(90, 78, 180), width=6)
    band = band.filter(ImageFilter.GaussianBlur(24))
    img = Image.blend(img, Image.blend(img, band, 0.5), 0.55)

    out = REPO / "assets" / "default_bg.png"
    out.parent.mkdir(exist_ok=True)
    img.save(out)
    print("已生成:", out, img.size)


if __name__ == "__main__":
    main()
