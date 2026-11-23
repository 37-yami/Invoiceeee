# -*- coding: utf-8 -*-
"""界面主题:暗色沉浸风格(类主流音乐/创作软件),扁平按钮体系。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS = {
    "root": "#12131b",        # 窗体最深(标题栏兜底)
    "dark": "#12131b",
    "dark_hover": "#1d1f2c",
    "dark_active": "#272a3d",
    "bg": "#191b26",          # 内容区底色
    "card": "#20222e",        # 卡片
    "card_soft": "#262938",   # 卡片内嵌块(芯片/预览)
    "border": "#262a3a",      # 弱化的描边(几乎不可见,靠明度区分)
    "accent": "#7c6ff0",      # 强调色(亮紫,暗底友好)
    "accent_hover": "#6a5ce6",
    "accent_soft": "#312c55",
    "text": "#e8eaf2",        # 亮字
    "text_on_dark": "#e8eaf2",
    "text_muted": "#8b90a6",
    "pending_bg": "#33301f",
    "warn": "#e8955c",
    "ok": "#5fc98e",
    "danger": "#e8955c",
}

FONT = "Microsoft YaHei"


def font(size: int = 10, bold: bool = False) -> tuple:
    return (FONT, size, "bold" if bold else "normal")


def btn(parent, text: str, command, kind: str = "secondary",
        **kwargs) -> tk.Button:
    """统一扁平按钮:primary 紫底白字 / secondary 深底亮字 / ghost 弱化 / danger。"""
    t = COLORS
    if kind == "primary":
        style = dict(bg=t["accent"], fg="#ffffff",
                     activebackground=t["accent_hover"],
                     activeforeground="#ffffff")
    elif kind == "danger":
        style = dict(bg=t["card"], fg=t["warn"],
                     activebackground="#3a2f26",
                     activeforeground=t["warn"])
    elif kind == "ghost":
        style = dict(bg=kwargs.pop("bg", t["card"]), fg=t["text_muted"],
                     activebackground=t["card_soft"],
                     activeforeground=t["text"])
    else:  # secondary
        style = dict(bg=t["card_soft"], fg=t["text"],
                     activebackground="#31354a",
                     activeforeground="#ffffff")
    common = dict(relief="flat", bd=0, cursor="hand2",
                  font=(FONT, 10, "bold"), padx=16, pady=7)
    common.update(style)
    common.update(kwargs)
    return tk.Button(parent, text=text, command=command, **common)


def card(parent, **kwargs) -> tk.Frame:
    """统一卡片:深色圆角感(1px 边框)。"""
    t = COLORS
    opts = dict(bg=t["card"], highlightthickness=0)
    opts.update(kwargs)
    return tk.Frame(parent, **opts)


class RoundedCard(tk.Canvas):
    """圆角卡片:底层是壁纸裁剪(圆角缺口透出真壁纸),
    其上是圆角矩形实色填充;子元素全部 pack 进 self.inner。

    用法:card = RoundedCard(parent, app); box(card.inner, ...).pack(...)
    """

    RADIUS = 14

    def __init__(self, parent, app, bg: str | None = None,
                 pad: int = 16):
        t = COLORS
        self.fill_color = bg or t["card"]
        super().__init__(parent, highlightthickness=0,
                         bg=t["bg"])
        self.app = app
        self.pad = pad
        self.inner = tk.Frame(self, bg=self.fill_color)
        self._bg_item = self.create_image(0, 0, anchor="nw")
        self._rect_item = self._draw_rounded(1, 1)
        self._win_item = self.create_window(
            self.pad, self.pad, anchor="nw", window=self.inner)
        self.bind("<Configure>", lambda _e: self._relayout())
        if hasattr(app, "register_card"):
            app.register_card(self)

    def _draw_rounded(self, w: int, h: int) -> int:
        r = min(self.RADIUS, w // 2, h // 2)
        pts = []
        steps = 6

        def arc(cx, cy, a0, a1):
            import math

            for i in range(steps + 1):
                a = math.radians(a0 + (a1 - a0) * i / steps)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

        x0, y0, x1, y1 = 0, 0, w, h
        arc(x1 - r, y1 - r, 0, 90)
        arc(x0 + r, y1 - r, 90, 180)
        arc(x0 + r, y0 + r, 180, 270)
        arc(x1 - r, y0 + r, 270, 360)
        flat = []
        for x, y in pts:
            flat.extend((x, y))
        return self.create_polygon(
            flat, smooth=True, fill=self.fill_color, outline="")

    def _relayout(self):
        w, h = max(self.winfo_width(), 2), max(self.winfo_height(), 2)
        self.delete(self._rect_item)
        self._rect_item = self._draw_rounded(w, h)
        self.coords(self._win_item, self.pad, self.pad)
        self.itemconfigure(
            self._win_item,
            width=max(w - 2 * self.pad, 1),
            height=max(h - 2 * self.pad, 1))
        # 标记顺序:壁纸图(最底) < 圆角矩形 < 内容
        self.tag_lower(self._bg_item)
        self.tag_raise(self._win_item)
        self.after_idle(self._sync_offset)

    def _sync_offset(self):
        """共享壁纸图按卡片在窗口中的位置负偏移,实现"透出背后的壁纸"。"""
        try:
            x = self.winfo_rootx() - self.app.winfo_rootx()
            y = self.winfo_rooty() - self.app.winfo_rooty()
            self.coords(self._bg_item, -x, -y)
        except Exception:
            pass

    def refresh_wallpaper(self, photo):
        """主窗口壁纸重绘后回调:更新底层图并对齐偏移。"""
        if photo is not None:
            self.itemconfigure(self._bg_item, image=photo)
            self.after_idle(self._sync_offset)
        else:
            self.itemconfigure(self._bg_item, image="")


def apply(root: tk.Tk | tk.Toplevel) -> None:
    """配置 ttk 控件为暗色(表格/输入框/下拉)。"""
    style = ttk.Style(root)
    t = COLORS
    style.configure("Treeview",
                    background=t["card"], fieldbackground=t["card"],
                    foreground=t["text"], rowheight=32,
                    font=(FONT, 10))
    style.configure("Treeview.Heading",
                    background="#262938", foreground=t["text_muted"],
                    font=(FONT, 9, "bold"), padding=(8, 7))
    style.map("Treeview",
              background=[("selected", t["accent"])],
              foreground=[("selected", "#ffffff")])
    style.configure("TEntry", padding=5,
                    fieldbackground=t["card_soft"],
                    background=t["card_soft"], foreground=t["text"],
                    insertcolor=t["text"])
    style.configure("TCombobox", padding=5,
                    fieldbackground=t["card_soft"],
                    background=t["card_soft"], foreground=t["text"],
                    arrowcolor=t["text_muted"])
    style.map("TCombobox",
              fieldbackground=[("readonly", t["card_soft"])],
              foreground=[("readonly", t["text"])])
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))
    root.option_add("*TCombobox*Listbox.background", t["card_soft"])
    root.option_add("*TCombobox*Listbox.foreground", t["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
