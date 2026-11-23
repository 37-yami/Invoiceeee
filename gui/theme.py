# -*- coding: utf-8 -*-
"""界面主题:暗色沉浸风格(类主流音乐/创作软件),扁平按钮体系。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS = {
    "root": "#12131b",        # 窗体最深(顶栏/侧栏/状态栏)
    "dark": "#12131b",
    "dark_hover": "#1d1f2c",
    "dark_active": "#272a3d",
    "bg": "#191b26",          # 内容区底色
    "card": "#20222e",        # 卡片
    "card_soft": "#262938",   # 卡片内嵌块(芯片/预览)
    "border": "#2c2f3f",
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
    style.update(highlightthickness=1, highlightbackground=t["border"])
    common = dict(relief="flat", bd=0, cursor="hand2",
                  font=(FONT, 10, "bold"), padx=14, pady=6)
    common.update(style)
    common.update(kwargs)
    return tk.Button(parent, text=text, command=command, **common)


def card(parent, **kwargs) -> tk.Frame:
    """统一卡片:深色圆角感(1px 边框)。"""
    t = COLORS
    opts = dict(bg=t["card"], highlightthickness=1,
                highlightbackground=t["border"])
    opts.update(kwargs)
    return tk.Frame(parent, **opts)


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
