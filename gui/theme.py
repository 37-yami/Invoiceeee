# -*- coding: utf-8 -*-
"""界面主题:配色、字体与 ttk 样式(扁平化,深色导航 + 浅色内容)。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS = {
    "dark": "#1f2430",        # 侧边栏 / 顶栏
    "dark_hover": "#2a3040",
    "dark_active": "#323b52",
    "accent": "#6c5ce7",      # 强调色
    "accent_soft": "#edeafc",
    "bg": "#f4f5f7",          # 内容区背景
    "card": "#ffffff",        # 卡片
    "border": "#e3e6ea",
    "text": "#1f2430",
    "text_on_dark": "#e8eaf0",
    "text_muted": "#7a8194",
    "pending_bg": "#fff8e1",
    "warn": "#b3541e",
    "ok": "#2c6e49",
}

FONT = "Microsoft YaHei"


def font(size: int = 10, bold: bool = False) -> tuple:
    return (FONT, size, "bold" if bold else "normal")


def apply(root: tk.Tk | tk.Toplevel) -> None:
    """配置 ttk 控件外观(表格/输入框/下拉),颜色取自 COLORS。"""
    style = ttk.Style(root)
    style.configure("Treeview",
                    background=COLORS["card"],
                    fieldbackground=COLORS["card"],
                    foreground=COLORS["text"],
                    rowheight=30,
                    font=(FONT, 10))
    style.configure("Treeview.Heading",
                    background="#eceef2",
                    foreground=COLORS["text"],
                    font=(FONT, 10, "bold"), padding=6)
    style.map("Treeview",
              background=[("selected", COLORS["accent"])],
              foreground=[("selected", "#ffffff")])
    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)
    style.configure("TButton", padding=(10, 6))
    style.configure("Accent.TButton", foreground="#ffffff")
