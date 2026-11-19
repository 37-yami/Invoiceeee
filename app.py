# -*- coding: utf-8 -*-
"""学生报销管家 · 桌面版入口。

用法:python app.py [--workspace 路径]
不指定工作区时,使用上次打开的目录;首次使用会弹出选择框。
"""
from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        description="学生报销管家:本地票据归档与报销汇总(桌面版,数据不离开本机)"
    )
    parser.add_argument("--workspace", default=None,
                        help="工作区目录(默认: 记住的上次目录)")
    args = parser.parse_args()

    from gui.main_window import launch

    launch(workspace=args.workspace)


if __name__ == "__main__":
    main()
