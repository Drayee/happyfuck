#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 路径解析（源码运行 / PyInstaller 冻结运行通用）。

冻结（exe）运行时：
- 资源（assets/）在打包解压目录 _MEIPASS 下；
- 可写数据（data/）放在 exe 同级目录，保证升级不丢配置。
"""
import os
import sys


def is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


def resource_base() -> str:
    """只读资源根目录（源码 = app/，冻结 = PyInstaller 解压目录）。"""
    if is_frozen():
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def exe_dir() -> str:
    """exe / 脚本所在目录。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))
