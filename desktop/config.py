#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 配置与持久化。"""
import json
import os
import sys

try:                     # 源码运行与 PyInstaller 冻结运行通用
    from paths import resource_base, exe_dir, is_frozen
except ImportError:      # 作为包内模块被导入时
    from .paths import resource_base, exe_dir, is_frozen

APP_NAME = 'HappyFuck乐奸'
APP_VERSION = '1.0.0'

HERE = os.path.dirname(os.path.abspath(__file__))
# tools 目录：源码运行 = 仓库根的 tools/；冻结运行 = tools 在 exe 同级 tools/
ROOT = os.path.dirname(HERE) if not is_frozen() else exe_dir()
TOOLS = os.path.join(ROOT, 'lib')
ASSETS = os.path.join(resource_base(), 'assets')
if is_frozen():
    # exe 同级目录，升级不丢配置
    DATA_DIR = os.path.join(exe_dir(), 'data')
else:
    DATA_DIR = os.path.join(HERE, 'data')

# 让 tools/ 下的模块（coord / run_sim / rules / legym_envelope / b_login_upload）
# 在任何 cwd 与冻结模式下都可导入
if TOOLS not in sys.path and os.path.isdir(TOOLS):
    sys.path.insert(0, TOOLS)

os.makedirs(DATA_DIR, exist_ok=True)


def _p(name):
    return os.path.join(DATA_DIR, name)


CONFIG_FILE = _p('config.json')
SESSION_FILE = _p('session.json')
RULES_FILE = _p('rules.json')
TRACKS_FILE = _p('tracks.json')
LOG_FILE = _p('app.log')


DEFAULTS = {
    'phone': '',
    'password': '',
    'school_id': '',
    'semester_id': '',
    'lgs_id': '',
    'scoring_type': '1',
    'entrance': '1',

    # 签名
    'hs_mode': 'frida',            # frida | table
    'hs_table': 'hs_table.json',
    'frida_host': '127.0.0.1:27042',

    # 运动
    'pace': 420,
    'duration': 1500,
    'noise': 0.9,
    'drop': 0.06,
    'sign_mode': 'all',

    # 定时
    'schedule_enabled': False,
    'schedule_times': ['07:30', '18:30'],
    'schedule_jitter_min': 20,     # 随机抖动 ±分钟
    'schedule_days': [1, 2, 3, 4, 5, 6, 7],

    # 安全
    'check_rules': True,
    'force_upload': False,
    'max_daily_km': 5.0,
    'min_interval_hours': 8,

    # 地图（范围跑核心：默认雅安校区围栏质心）
    'map_center': [29.980193, 102.995812],
    'map_zoom': 16,
    'map_sat': False,

    # 界面
    'tray_on_close': True,
    'start_minimized': False,
}


class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.data.update(json.load(f))
            except Exception:
                pass
        return self.data

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, k, default=None):
        return self.data.get(k, default if default is not None else DEFAULTS.get(k))

    def set(self, k, v):
        self.data[k] = v

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
