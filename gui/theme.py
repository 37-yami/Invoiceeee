# -*- coding: utf-8 -*-
"""界面主题:配色、字体、扁平按钮体系与 ttk 样式。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS = {
    "dark": "#1b2030",        # 侧边栏 / 顶栏
    "dark_hover": "#242b40",
    "dark_active": "#2c3550",
    "accent": "#6c5ce7",      # 强调色(紫)
    "accent_hover": "#5a4bd4",
    "accent_soft": "#edeafc",
    "bg": "#f4f5f8",          # 内容区背景
    "card": "#ffffff",        # 卡片
    "border": "#e6e8ef",
    "text": "#232735",
    "text_on_dark": "#e8eaf2",
    "text_muted": "#7b8194",
    "pending_bg": "#fff8e1",
    "warn": "#b3541e",
    "ok": "#2c6e49",
}

FONT = "Microsoft YaHei"


def font(size: int = 10, bold: bool = False) -> tuple:
    return (FONT, size, "bold" if bold else "normal")


def btn(parent, text: str, command, kind: str = "secondary",
        **kwargs) -> tk.Button:
    """统一扁平按钮:primary 紫底白字 / secondary 白底紫字 / ghost 透明灰字 / danger。
    替代 ttk 默认灰按钮,保证全局观感一致。"""
    t = COLORS
    if kind == "primary":
        style = dict(bg=t["accent"], fg="#ffffff",
                     activebackground=t["accent_hover"],
                     activeforeground="#ffffff")
    elif kind == "danger":
        style = dict(bg=t["card"], fg=t["warn"],
                     activebackground="#fdf1ea",
                     activeforeground=t["warn"])
    elif kind == "ghost":
        style = dict(bg=kwargs.pop("bg", t["card"]), fg=t["text_muted"],
                     activebackground=t["bg"],
                     activeforeground=t["text"])
    else:  # secondary
        style = dict(bg=t["card"], fg=t["accent"],
                     activebackground=t["accent_soft"],
                     activeforeground=t["accent"])
    if kind != "ghost":
        style.update(highlightthickness=1,
                     highlightbackground=t["border"])
    common = dict(relief="flat", bd=0, cursor="hand2",
                  font=(FONT, 10, "bold"), padx=14, pady=6)
    common.update(style)
    common.update(kwargs)
    return tk.Button(parent, text=text, command=command, **common)


def nav_btn(parent, text: str, command) -> tk.Button:
    """侧边栏导航按钮。"""
    t = COLORS
    return tk.Button(parent, text=text, anchor="w", bg=t["dark"],
                     fg=t["text_on_dark"],
                     activebackground=t["dark_active"],
                     activeforeground="#ffffff", relief="flat", bd=0,
                     pady=11, padx=20, font=(FONT, 11), cursor="hand2",
                     command=command)


def apply(root: tk.Tk | tk.Toplevel) -> None:
    """配置 ttk 控件(表格/输入框/下拉)外观。"""
    style = ttk.Style(root)
    style.configure("Treeview",
                    background=COLORS["card"],
                    fieldbackground=COLORS["card"],
                    foreground=COLORS["text"],
                    rowheight=32, font=(FONT, 10))
    style.configure("Treeview.Heading",
                    background="#eef0f5", foreground=COLORS["text_muted"],
                    font=(FONT, 9, "bold"), padding=(8, 7))
    style.map("Treeview",
              background=[("selected", COLORS["accent"])],
              foreground=[("selected", "#ffffff")])
    style.configure("TEntry", padding=5)
    style.configure("TCombobox", padding=5)
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))
