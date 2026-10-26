#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 主窗口。"""
import json
import math
import os
import sys
import time
from datetime import datetime

from PyQt6.QtCore import (Qt, QTimer, pyqtSignal, QSize, QThread, QObject)
from PyQt6.QtGui import QIcon, QAction, QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QTabWidget, QScrollArea, QFrame, QTextEdit, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QSystemTrayIcon,
    QMenu, QSizePolicy, QProgressBar, QGroupBox, QGridLayout, QTimeEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QFileDialog)

from PyQt6.QtCore import QTime

import config as CFG
import theme as TH
from theme import C
from widgets import HelpButton, LabeledRow, SectionTitle, StatusPill, toast
from map_panel import MapPanel
from service import Service, Session
from scheduler import Scheduler

# 范围跑核心：直接复用 tools/rules.py 与 run_sim.py 的几何与规则解析
if CFG.TOOLS not in sys.path:
    sys.path.insert(0, CFG.TOOLS)
import rules as R
import run_sim as RUNSIM


# ---------------------------------------------------------------------------
HELP = {
    'login': (
        '账号登录',
        '用乐健体育 App 的**手机号 + 密码**登录。\n\n'
        '这就是 App 自己的登录接口：\n'
        'POST authorization/user/v2/manage/login\n\n'
        '实测结论（2026-10-20）：\n'
        '· 服务端**不校验登录签名**，无需配置任何签名即可登录\n'
        '· 登录后自动拿到 accessToken、schoolId\n'
        '· token 会过期，程序会自动用 refreshToken 续期\n\n'
        '如果提示密码错误，用的是乐健 App 的密码，\n'
        '不是学校教务系统密码。'),
    'hs_mode': (
        '签名方式',
        '上传接口带一个 signDigital 签名（Rengis.hs()），\n'
        '该函数被 DexVMP 加固，无法离线计算。\n\n'
        '【Frida 实时签名】手机连电脑跑 frida-server，\n'
        '每次签名实时算。\n\n'
        '【查表签名】提前抓一次签名表离线查。\n\n'
        '注意：登录**不需要**签名，只有上传可能需要。\n'
        '上传是否真的校验签名，以抓包校准后的实测为准。'),
    'school': (
        '学校与学期',
        '登录后会自动填好，一般不用改。\n\n'
        'semesterId：当前学期编号\n'
        'limitationsGoalsSexInfoId：学校的跑步规则编号\n'
        'schoolId：学校编号，上传时放在 Organization 头里\n\n'
        '如果上传报「规则不存在」，就是这几个 ID 不对，\n'
        '点「刷新规则」重新拉一次。'),
    'map': (
        '地图操作',
        '在地图上点出你学校的操场跑道：\n\n'
        '· 左键点击 = 添加一个跑道顶点\n'
        '· 右键顶点 = 删除该顶点\n'
        '· 拖动顶点 = 微调位置\n'
        '· 「闭合跑道」= 把最后一个点和第一个点连起来\n\n'
        '红色虚线框是学校规定的跑步范围，\n'
        '红色圆圈 S0/S1 是必须经过的打卡点。\n\n'
        '建议沿真实跑道点一圈，4~8 个点就够了。'),
    'fetch_rules': (
        '刷新学校规则',
        '从服务器拉取你学校的跑步规则：\n'
        '· 配速允许范围\n'
        '· 单次里程上下限\n'
        '· 日/周/学期配额\n'
        '· 打卡点位置\n'
        '· 跑步范围围栏\n\n'
        '拉取后地图上会画出围栏和打卡点，\n'
        '右侧「规则」页会显示所有限制。'),
    'pace': (
        '目标配速',
        '跑 1 公里需要多少秒。\n\n'
        '参考：\n'
        '· 慢跑 7分/公里 = 420 秒\n'
        '· 正常 6分/公里 = 360 秒\n'
        '· 快跑 5分/公里 = 300 秒\n\n'
        '点「按规则自动填」会取学校允许区间的中值，\n'
        '这样最不容易被判无效。'),
    'duration': (
        '运动时长',
        '这次跑步持续多少秒。\n\n'
        '时长 × 速度 = 里程。\n'
        '系统会自动算出里程，并检查是否在学校允许范围内。'),
    'noise': (
        'GPS 噪声',
        '模拟真实手机 GPS 的抖动，单位米。\n\n'
        '真实手机在操场上通常 0.5~1.5 米。\n'
        '设太小（0）会让轨迹过于完美，反而可疑。\n'
        '建议保持 0.8~1.2。'),
    'drop': (
        '丢点率',
        '模拟 GPS 信号丢失的概率。\n\n'
        '真实跑步时会有少量采样点丢失（进树下、贴墙跑）。\n'
        '建议 0.03~0.10。\n'
        '设 0 会让采样点数量过于整齐。'),
    'sign_mode': (
        '打卡点策略',
        '怎么处理学校的打卡点。\n\n'
        '【全部】每个打卡点都会经过（最安全）\n'
        '【隔一】隔一个经过一个\n'
        '【无】不经过打卡点（可能被判无效）\n\n'
        '如果学校规则里没有打卡点要求，这个选项无效。'),
    'schedule': (
        '定时任务',
        '设置每天自动刷的时间点。\n\n'
        '· 可加多个时间点\n'
        '· 抖动：在设定时间前后随机偏移，避免每天分秒不差\n'
        '· 星期：只在选中的星期执行\n\n'
        '建议每天 1~2 次，间隔 8 小时以上。\n'
        '刷太频繁是封号的主要诱因之一。'),
    'check_rules': (
        '上传前体检',
        '上传前先检查数据是否符合学校规则：\n'
        '· 配速在允许区间内\n'
        '· 里程在上下限内\n'
        '· 打卡点数量够\n'
        '· 轨迹全在围栏内\n'
        '· 相邻采样点距离合规\n\n'
        '强烈建议保持开启。不通过时会被拦下，\n'
        '避免产生「无效记录」影响账号。'),
    'force': (
        '强制上传',
        '体检不通过时仍然上传。\n\n'
        '⚠ 不建议开启。\n'
        '违规数据会被服务端记为「无效记录」，\n'
        '多次无效可能触发风控。'),
    'daily_limit': (
        '每日里程上限',
        '每天最多刷多少公里。\n\n'
        '这是本地保护，不是服务器规则。\n'
        '建议设成学校要求的一半左右，\n'
        '留出余量避免异常。'),
    'interval': (
        '最小间隔',
        '两次刷之间至少隔多少小时。\n\n'
        '真实学生不会一天跑好几次。\n'
        '建议 8 小时以上。'),
}


# ---------------------------------------------------------------------------
class _UiPump(QObject):
    """跨线程 UI 回调泵。

    service 的回调都跑在 Python 裸线程里，而 QTimer.singleShot 在
    非主线程不生效（QTimer 只在其创建线程工作）。这里用一个主线程
    创建的 QObject + 信号（跨线程自动 QueuedConnection）把闭包安全地
    投递回主线程执行。
    """
    fire = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.fire.connect(self._run)

    @staticmethod
    def _run(fn):
        try:
            fn()
        except Exception:
            import traceback
            traceback.print_exc()


# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = CFG.Config()
        self.svc = Service(self.cfg)
        self._pump = _UiPump()
        self._post_ui = self._pump.fire.emit
        self.sched = Scheduler(self.svc, self.cfg,
                               on_fire=self._on_schedule_fire,
                               on_log=lambda m: self.svc.log.info('[调度] ' + m))

        self.waypoints = []
        self.closed = False
        self._suppress_path_sync = False
        self.last_vo = None
        self.last_stats = None
        self.run_points = []
        self._run_anim_idx = 0
        self._anim_timer = None

        self.setWindowTitle('%s v%s' % (CFG.APP_NAME, CFG.APP_VERSION))
        self.resize(1380, 860)
        self.setMinimumSize(1100, 700)

        self._build_ui()
        self._load_state()
        self._start_timers()

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)

        # 左：地图
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        self.map = MapPanel()
        self.map.ready.connect(self._on_map_ready)
        self.map.mapClicked.connect(self._on_map_click)
        self.map.deleteRequested.connect(self._on_map_delete)
        self.map.pathChanged.connect(self._on_path_changed)
        self.map.mouseMoved.connect(self._on_mouse_move)
        ll.addWidget(self.map, 1)
        ll.addWidget(self._build_map_toolbar())

        body.addWidget(left)

        # 右：面板
        self.side = self._build_side()
        body.addWidget(self.side)

        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 0)
        body.setSizes([900, 470])
        root.addWidget(body, 1)

        root.addWidget(self._build_bottombar())

    # ------------------------------------------------------------------
    def _build_topbar(self):
        bar = QWidget()
        bar.setObjectName('TopBar')
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)

        title = QLabel('乐奸')
        title.setObjectName('Title')
        lay.addWidget(title)

        ver = QLabel('v' + CFG.APP_VERSION)
        ver.setObjectName('Subtitle')
        lay.addWidget(ver)

        lay.addSpacing(20)

        self.pill_account = StatusPill('未登录', 'idle')
        lay.addWidget(self.pill_account)

        self.pill_rules = StatusPill('规则未加载', 'idle')
        lay.addWidget(self.pill_rules)

        self.pill_sched = StatusPill('调度停止', 'idle')
        lay.addWidget(self.pill_sched)

        lay.addStretch(1)

        self.lb_next = QLabel('')
        self.lb_next.setStyleSheet('color:%s;' % C['fg_dim'])
        lay.addWidget(self.lb_next)

        btn_help = QPushButton('使用说明')
        btn_help.clicked.connect(self._show_guide)
        lay.addWidget(btn_help)

        return bar

    # ------------------------------------------------------------------
    def _build_map_toolbar(self):
        bar = QWidget()
        bar.setFixedHeight(46)
        bar.setStyleSheet('background:%s;border-top:1px solid %s;'
                          % (C['bg2'], C['border']))
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        lay.addWidget(QLabel('跑道:'))
        self.lb_path = QLabel('未绘制')
        self.lb_path.setStyleSheet('color:%s;font-weight:bold;' % C['accent'])
        lay.addWidget(self.lb_path)

        lay.addSpacing(12)

        b = QPushButton('闭合跑道')
        b.clicked.connect(self._toggle_close)
        lay.addWidget(b)

        b = QPushButton('撤销一点')
        b.clicked.connect(self._undo_point)
        lay.addWidget(b)

        b = QPushButton('清空')
        b.clicked.connect(self._clear_path)
        lay.addWidget(b)

        lay.addSpacing(8)
        b = QPushButton('📍 定位到学校')
        b.clicked.connect(self._goto_school)
        lay.addWidget(b)

        b = QPushButton('🏃 用围栏生成跑道')
        b.clicked.connect(self._gen_from_fence)
        b.setStyleSheet('background:%s;color:#fff;font-weight:bold;'
                        % C['accent'])
        lay.addWidget(b)

        self.cb_sat = QCheckBox('卫星图')
        self.cb_sat.toggled.connect(lambda v: self.map.set_sat(v))
        lay.addWidget(self.cb_sat)

        lay.addStretch(1)

        self.lb_coord = QLabel('--')
        self.lb_coord.setStyleSheet('color:%s;font:11px Consolas;'
                                    % C['fg_mute'])
        lay.addWidget(self.lb_coord)

        return bar

    # ------------------------------------------------------------------
    def _build_side(self):
        panel = QWidget()
        panel.setObjectName('SidePanel')
        panel.setMinimumWidth(430)
        panel.setMaximumWidth(560)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_account(), '账号')
        self.tabs.addTab(self._tab_rules(), '规则')
        self.tabs.addTab(self._tab_run(), '刷步')
        self.tabs.addTab(self._tab_schedule(), '定时')
        self.tabs.addTab(self._tab_log(), '日志')
        self.tabs.addTab(self._tab_settings(), '设置')
        lay.addWidget(self.tabs, 1)

        return panel

    # ------------------------------------------------------------------
    def _tab_account(self):
        w = QWidget()
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        lay.addWidget(SectionTitle('登录', '账号登录', HELP['login']))

        self.ed_phone = QLineEdit()
        self.ed_phone.setPlaceholderText('手机号')
        lay.addWidget(LabeledRow('手机号', self.ed_phone,
                                 '手机号', HELP['login'], 70))

        self.ed_pass = QLineEdit()
        self.ed_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_pass.setPlaceholderText('密码')
        lay.addWidget(LabeledRow('密码', self.ed_pass,
                                 '密码', HELP['login'], 70))

        row = QHBoxLayout()
        self.btn_login = QPushButton('登录')
        self.btn_login.setObjectName('Primary')
        self.btn_login.clicked.connect(self._do_login)
        row.addWidget(self.btn_login, 1)
        lay.addLayout(row)

        # 账号状态
        lay.addWidget(SectionTitle('账号状态'))

        self.lb_user = QLabel('未登录')
        self.lb_user.setStyleSheet('color:%s;' % C['fg'])
        lay.addWidget(self.lb_user)

        self.lb_school = QLabel('--')
        self.lb_school.setStyleSheet('color:%s;' % C['fg_dim'])
        lay.addWidget(self.lb_school)

        # 配额状态
        self.lb_quota = QLabel('今日 0.00 km · 本周 0.00 km')
        self.lb_quota.setWordWrap(True)
        self.lb_quota.setStyleSheet(
            'color:%s;background:%s;border:1px solid %s;'
            'border-radius:5px;padding:8px;'
            % (C['fg_dim'], C['bg2'], C['border']))
        lay.addWidget(self.lb_quota)

        lay.addWidget(SectionTitle('学校与学期', '学校与学期', HELP['school']))

        self.ed_semester = QLineEdit()
        lay.addWidget(LabeledRow('semesterId', self.ed_semester,
                                 '学校与学期', HELP['school'], 100))

        self.ed_lgs = QLineEdit()
        lay.addWidget(LabeledRow('lgsId', self.ed_lgs,
                                 '学校与学期', HELP['school'], 100))

        self.ed_school = QLineEdit()
        lay.addWidget(LabeledRow('schoolId', self.ed_school,
                                 '学校与学期', HELP['school'], 100))

        self.btn_refresh_rules = QPushButton('刷新规则')
        self.btn_refresh_rules.clicked.connect(self._do_fetch_rules)
        lay.addWidget(self.btn_refresh_rules)

        lay.addWidget(SectionTitle('签名', '签名方式', HELP['hs_mode']))

        self.cb_hs = QComboBox()
        self.cb_hs.addItems(['Frida 实时签名', '查表签名'])
        self.cb_hs.currentIndexChanged.connect(self._on_hs_changed)
        lay.addWidget(LabeledRow('方式', self.cb_hs,
                                 '签名方式', HELP['hs_mode'], 70))

        self.ed_frida = QLineEdit()
        lay.addWidget(LabeledRow('Frida 地址', self.ed_frida,
                                 '签名方式', HELP['hs_mode'], 90))

        self.ed_hstable = QLineEdit()
        lay.addWidget(LabeledRow('签名表', self.ed_hstable,
                                 '签名方式', HELP['hs_mode'], 90))

        self.btn_check_hs = QPushButton('检查签名是否可用')
        self.btn_check_hs.clicked.connect(self._do_check_hs)
        lay.addWidget(self.btn_check_hs)

        self.lb_hs_state = QLabel('未检查')
        self.lb_hs_state.setWordWrap(True)
        self.lb_hs_state.setStyleSheet(
            'color:%s;background:%s;border:1px solid %s;'
            'border-radius:5px;padding:6px;font-size:11px;'
            % (C['fg_mute'], C['bg2'], C['border']))
        lay.addWidget(self.lb_hs_state)

        lay.addStretch(1)
        sc.setWidget(inner)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(sc)
        return w

    # ------------------------------------------------------------------
    def _tab_rules(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        lay.addWidget(SectionTitle('学校限制', '刷新学校规则', HELP['fetch_rules']))

        self.tbl_rules = QTableWidget(0, 2)
        self.tbl_rules.setHorizontalHeaderLabels(['项目', '值'])
        self.tbl_rules.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_rules.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.tbl_rules.verticalHeader().setVisible(False)
        self.tbl_rules.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_rules.setAlternatingRowColors(False)
        lay.addWidget(self.tbl_rules, 1)

        self.lb_rule_summary = QLabel('尚未加载规则')
        self.lb_rule_summary.setWordWrap(True)
        self.lb_rule_summary.setStyleSheet(
            'color:%s;background:%s;border:1px solid %s;'
            'border-radius:5px;padding:8px;'
            % (C['fg_dim'], C['bg2'], C['border']))
        lay.addWidget(self.lb_rule_summary)

        b = QPushButton('刷新规则')
        b.clicked.connect(self._do_fetch_rules)
        lay.addWidget(b)

        return w

    # ------------------------------------------------------------------
    def _tab_run(self):
        w = QWidget()
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        lay.addWidget(SectionTitle('运动参数'))

        self.sp_pace = QSpinBox()
        self.sp_pace.setRange(120, 1200)
        self.sp_pace.setSuffix(' 秒/公里')
        lay.addWidget(LabeledRow('目标配速', self.sp_pace,
                                 '目标配速', HELP['pace'], 80))

        self.sp_duration = QSpinBox()
        self.sp_duration.setRange(60, 14400)
        self.sp_duration.setSuffix(' 秒')
        lay.addWidget(LabeledRow('时长', self.sp_duration,
                                 '运动时长', HELP['duration'], 80))

        row = QHBoxLayout()
        b = QPushButton('按规则自动填')
        b.clicked.connect(self._auto_fill)
        row.addWidget(b)
        b = QPushButton('随机变化')
        b.clicked.connect(self._randomize)
        row.addWidget(b)
        lay.addLayout(row)

        self.sp_noise = QDoubleSpinBox()
        self.sp_noise.setRange(0, 5)
        self.sp_noise.setSingleStep(0.1)
        self.sp_noise.setDecimals(2)
        self.sp_noise.setSuffix(' 米')
        lay.addWidget(LabeledRow('GPS 噪声', self.sp_noise,
                                 'GPS 噪声', HELP['noise'], 80))

        self.sp_drop = QDoubleSpinBox()
        self.sp_drop.setRange(0, 0.5)
        self.sp_drop.setSingleStep(0.01)
        self.sp_drop.setDecimals(2)
        lay.addWidget(LabeledRow('丢点率', self.sp_drop,
                                 '丢点率', HELP['drop'], 80))

        self.cb_sign = QComboBox()
        self.cb_sign.addItems(['全部打卡点', '隔一个打卡', '不打卡'])
        lay.addWidget(LabeledRow('打卡点', self.cb_sign,
                                 '打卡点策略', HELP['sign_mode'], 80))

        lay.addWidget(SectionTitle('执行'))

        self.btn_preview = QPushButton('预览轨迹')
        self.btn_preview.clicked.connect(self._do_preview)
        lay.addWidget(self.btn_preview)

        self.btn_run = QPushButton('开始刷')
        self.btn_run.setObjectName('Success')
        self.btn_run.setMinimumHeight(38)
        self.btn_run.clicked.connect(self._do_run)
        lay.addWidget(self.btn_run)

        # 上传校准状态
        self.lb_upload_ready = QLabel('')
        self.lb_upload_ready.setWordWrap(True)
        self.lb_upload_ready.setStyleSheet(
            'color:%s;background:%s;border:1px solid %s;'
            'border-radius:5px;padding:6px;font-size:11px;'
            % (C['fg_dim'], C['bg2'], C['border']))
        lay.addWidget(self.lb_upload_ready)

        btn_cap = QPushButton('上传校准说明')
        btn_cap.clicked.connect(self._show_capture_help)
        lay.addWidget(btn_cap)
        self._refresh_upload_ready()

        # 实时状态
        lay.addWidget(SectionTitle('实时状态'))

        self.lb_live_pos = QLabel('--')
        self.lb_live_pos.setStyleSheet('color:%s;font:11px Consolas;'
                                       % C['fg_dim'])
        lay.addWidget(self.lb_live_pos)

        self.lb_live_pace = QLabel('--')
        self.lb_live_pace.setStyleSheet(
            'color:%s;font:bold 22px "Consolas";' % C['accent2'])
        lay.addWidget(self.lb_live_pace)

        self.lb_live_dist = QLabel('--')
        self.lb_live_dist.setStyleSheet('color:%s;font:11px Consolas;'
                                        % C['fg_dim'])
        lay.addWidget(self.lb_live_dist)

        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        lay.addWidget(self.prog)

        lay.addStretch(1)
        sc.setWidget(inner)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(sc)
        return w

    # ------------------------------------------------------------------
    def _tab_schedule(self):
        w = QWidget()
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        lay.addWidget(SectionTitle('定时刷', '定时任务', HELP['schedule']))

        self.cb_sched = QCheckBox('启用定时任务')
        self.cb_sched.toggled.connect(self._on_sched_toggle)
        lay.addWidget(self.cb_sched)

        lay.addWidget(QLabel('时间点（可多个）'))
        self.lst_times = QListWidget()
        self.lst_times.setMaximumHeight(110)
        lay.addWidget(self.lst_times)

        row = QHBoxLayout()
        self.te_new = QTimeEdit()
        self.te_new.setDisplayFormat('HH:mm')
        self.te_new.setTime(QTime(7, 30))
        row.addWidget(self.te_new, 1)
        b = QPushButton('添加')
        b.clicked.connect(self._add_time)
        row.addWidget(b)
        b = QPushButton('删除')
        b.clicked.connect(self._del_time)
        row.addWidget(b)
        lay.addLayout(row)

        self.sp_jitter = QSpinBox()
        self.sp_jitter.setRange(0, 120)
        self.sp_jitter.setSuffix(' 分钟')
        lay.addWidget(LabeledRow('随机抖动', self.sp_jitter,
                                 '定时任务', HELP['schedule'], 80))

        lay.addWidget(QLabel('执行星期'))
        self.day_checks = []
        day_row = QHBoxLayout()
        for i, n in enumerate(['一', '二', '三', '四', '五', '六', '日']):
            cb = QCheckBox(n)
            cb.setChecked(True)
            self.day_checks.append(cb)
            day_row.addWidget(cb)
        lay.addLayout(day_row)

        lay.addSpacing(8)
        row = QHBoxLayout()
        self.btn_sched_start = QPushButton('启动调度')
        self.btn_sched_start.setObjectName('Primary')
        self.btn_sched_start.clicked.connect(self._start_sched)
        row.addWidget(self.btn_sched_start)
        self.btn_sched_stop = QPushButton('停止')
        self.btn_sched_stop.clicked.connect(self._stop_sched)
        row.addWidget(self.btn_sched_stop)
        lay.addLayout(row)

        self.lb_sched_state = QLabel('未启动')
        self.lb_sched_state.setWordWrap(True)
        self.lb_sched_state.setStyleSheet(
            'color:%s;background:%s;border:1px solid %s;'
            'border-radius:5px;padding:8px;'
            % (C['fg_dim'], C['bg2'], C['border']))
        lay.addWidget(self.lb_sched_state)

        lay.addWidget(SectionTitle('安全保护'))
        self.sp_daily = QDoubleSpinBox()
        self.sp_daily.setRange(0, 50)
        self.sp_daily.setSingleStep(0.5)
        self.sp_daily.setSuffix(' 公里')
        lay.addWidget(LabeledRow('每日上限', self.sp_daily,
                                 '每日里程上限', HELP['daily_limit'], 80))

        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(0, 72)
        self.sp_interval.setSuffix(' 小时')
        lay.addWidget(LabeledRow('最小间隔', self.sp_interval,
                                 '最小间隔', HELP['interval'], 80))

        lay.addStretch(1)
        sc.setWidget(inner)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(sc)
        return w

    # ------------------------------------------------------------------
    def _tab_log(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        # 上传历史
        lay.addWidget(SectionTitle('上传记录'))

        self.tbl_hist = QTableWidget(0, 4)
        self.tbl_hist.setHorizontalHeaderLabels(['时间', '里程', '配速', '结果'])
        self.tbl_hist.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.tbl_hist.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_hist.verticalHeader().setVisible(False)
        self.tbl_hist.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_hist.setMaximumHeight(200)
        lay.addWidget(self.tbl_hist)

        lay.addWidget(SectionTitle('运行日志'))

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet(
            'background:%s;color:%s;font:11px Consolas;border-radius:5px;'
            % (C['bg0'], C['fg_dim']))
        lay.addWidget(self.txt_log, 1)

        row = QHBoxLayout()
        b = QPushButton('刷新')
        b.clicked.connect(self._refresh_history)
        row.addWidget(b)
        b = QPushButton('清空日志')
        b.clicked.connect(lambda: self.txt_log.clear())
        row.addWidget(b)
        b = QPushButton('导出日志')
        b.clicked.connect(self._export_log)
        row.addWidget(b)
        lay.addLayout(row)

        return w

    def _refresh_history(self):
        """刷新上传历史表。"""
        recs = self.svc.history.recent(20)
        self.tbl_hist.setRowCount(len(recs))
        for i, r in enumerate(recs):
            ts = (r.get('ts') or '')[5:16].replace('T', ' ')
            km = '%.2f km' % r.get('km', 0)
            pace = '%.0f' % r.get('pace', 0) if r.get('pace') else '--'
            ok = r.get('ok')
            result = '成功' if ok else (r.get('msg') or '失败')[:20]

            self.tbl_hist.setItem(i, 0, QTableWidgetItem(ts))
            self.tbl_hist.setItem(i, 1, QTableWidgetItem(km))
            self.tbl_hist.setItem(i, 2, QTableWidgetItem(pace))
            it = QTableWidgetItem(result)
            it.setForeground(QColor(C['accent2'] if ok else C['err']))
            self.tbl_hist.setItem(i, 3, it)

        # 更新配额标签
        st = self.svc.history.stats()
        parts = ['今日 %.2f km' % st['today_km'],
                 '本周 %.2f km' % st['week_km'],
                 '今日 %d 次' % st['today_count']]
        if st['hours_since'] is not None:
            parts.append('距上次 %.1f 小时' % st['hours_since'])
        if st['fails'] > 0:
            parts.append('⚠ 连续失败 %d 次' % st['fails'])
        self.lb_quota.setText(' · '.join(parts))
        if st['fails'] >= 3:
            self.lb_quota.setStyleSheet(
                'color:%s;background:#3a1e1e;border:1px solid #5a2d2d;'
                'border-radius:5px;padding:8px;' % C['err'])
        else:
            self.lb_quota.setStyleSheet(
                'color:%s;background:%s;border:1px solid %s;'
                'border-radius:5px;padding:8px;'
                % (C['fg_dim'], C['bg2'], C['border']))

    # ------------------------------------------------------------------
    def _tab_settings(self):
        w = QWidget()
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        lay.addWidget(SectionTitle('安全', '上传前体检', HELP['check_rules']))

        self.cb_check = QCheckBox('上传前体检（推荐）')
        lay.addWidget(self.cb_check)

        self.cb_force = QCheckBox('强制上传（不建议）')
        lay.addWidget(self.cb_force)

        lay.addWidget(SectionTitle('界面'))
        self.cb_tray = QCheckBox('关闭窗口时最小化到托盘')
        lay.addWidget(self.cb_tray)

        lay.addWidget(SectionTitle('数据'))
        row = QHBoxLayout()
        b = QPushButton('打开数据目录')
        b.clicked.connect(self._open_data_dir)
        row.addWidget(b)
        lay.addLayout(row)

        b = QPushButton('重置配置')
        b.setObjectName('Danger')
        b.clicked.connect(self._reset_config)
        lay.addWidget(b)

        lay.addStretch(1)
        sc.setWidget(inner)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(sc)
        return w

    # ------------------------------------------------------------------
    def _build_bottombar(self):
        bar = QWidget()
        bar.setObjectName('BottomBar')
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 2, 12, 2)
        lay.setSpacing(10)

        self.lb_status = QLabel('就绪')
        self.lb_status.setStyleSheet('color:%s;' % C['fg_dim'])
        lay.addWidget(self.lb_status)

        lay.addStretch(1)

        self.lb_ver = QLabel('%s v%s' % (CFG.APP_NAME, CFG.APP_VERSION))
        self.lb_ver.setStyleSheet('color:%s;' % C['fg_mute'])
        lay.addWidget(self.lb_ver)

        return bar

    # ------------------------------------------------------------------
    # 状态同步
    # ------------------------------------------------------------------
    def _load_state(self):
        c = self.cfg
        self.ed_phone.setText(c.get('phone') or '')
        self.ed_pass.setText(c.get('password') or '')
        self.ed_semester.setText(c.get('semester_id') or '')
        self.ed_lgs.setText(c.get('lgs_id') or '')
        self.ed_school.setText(c.get('school_id') or '')

        self.cb_hs.setCurrentIndex(0 if c.get('hs_mode') == 'frida' else 1)
        self.ed_frida.setText(c.get('frida_host') or '')
        self.ed_hstable.setText(c.get('hs_table') or '')

        self.sp_pace.setValue(int(c.get('pace') or 420))
        self.sp_duration.setValue(int(c.get('duration') or 1500))
        self.sp_noise.setValue(float(c.get('noise') or 0.9))
        self.sp_drop.setValue(float(c.get('drop') or 0.06))
        sm = c.get('sign_mode') or 'all'
        self.cb_sign.setCurrentIndex({'all': 0, 'alt': 1, 'none': 2}.get(sm, 0))

        self.cb_sched.setChecked(bool(c.get('schedule_enabled')))
        self.sp_jitter.setValue(int(c.get('schedule_jitter_min') or 20))
        self.sp_daily.setValue(float(c.get('max_daily_km') or 3.0))
        self.sp_interval.setValue(int(c.get('min_interval_hours') or 8))

        for t in (c.get('schedule_times') or []):
            self.lst_times.addItem(t)
        if self.lst_times.count() == 0:
            for t in ['07:30', '18:30']:
                self.lst_times.addItem(t)

        days = c.get('schedule_days') or [1, 2, 3, 4, 5, 6, 7]
        for i, cb in enumerate(self.day_checks):
            cb.setChecked((i + 1) in days)

        self.cb_check.setChecked(bool(c.get('check_rules')))
        self.cb_force.setChecked(bool(c.get('force_upload')))
        self.cb_tray.setChecked(bool(c.get('tray_on_close')))

        # 会话
        if self.svc.session.valid:
            self._update_account_ui()
            self.pill_account.set_text(
                self.svc.session.real_name or self.svc.session.mobile or '已登录',
                'ok')
            self.lb_user.setText('已登录: %s' % (
                self.svc.session.real_name or self.svc.session.mobile))
            self.lb_school.setText(self.svc.session.school_name or '--')

            # token 快过期才续（阈值 2h；token 寿命约 8h，阈值过大
            # 会导致每次启动都无谓续期）
            raw = self.svc.session.raw.get('data') or {}
            exp = raw.get('accessTokenExpires') or 0
            import time as _t
            if exp and _t.time() * 1000 > exp - 7200000:
                self.svc.log.info('token 即将过期，自动续期')
                self.svc.refresh_token(on_done=lambda ok, m: (
                    self.svc.log.ok('自动续期成功') if ok
                    else self.svc.log.error('自动续期失败: %s' % m)))

        # 缓存规则
        rs = self.svc.load_cached_rules()
        if rs:
            self._render_rules(rs)
            self.pill_rules.set_text('规则已加载', 'ok')

        self._refresh_log()

    def _update_account_ui(self):
        s = self.svc.session
        self.lb_user.setText('已登录: %s' % (s.real_name or s.mobile or s.user_id))
        self.lb_school.setText('%s (%s)' % (s.school_name or '--',
                                            s.school_id or '--'))
        if not self.ed_semester.text():
            self.ed_semester.setText(s.semester_id or '')
        if not self.ed_lgs.text():
            self.ed_lgs.setText(s.lgs_id or '')
        if not self.ed_school.text():
            self.ed_school.setText(s.school_id or '')

    def _render_rules(self, rs):
        d = rs.raw or {}
        rows = []

        def add(k, label, fmt=None):
            v = d.get(k)
            if v is None or v == '':
                return
            if fmt:
                try:
                    v = fmt(v)
                except Exception:
                    pass
            rows.append((label, str(v)))

        add('limitationsGoalsSexInfoId', '规则ID')
        add('semesterId', '学期')
        add('scoringType', '计分类型')

        if rs.pace_min and rs.pace_max:
            lo, hi = sorted([rs.pace_min, rs.pace_max])
            rows.append(('配速区间', '%d ~ %d 秒/公里' % (lo, hi)))
        if rs.cad_min and rs.cad_max:
            rows.append(('步频区间', '%s ~ %s 步/分' % (rs.cad_min, rs.cad_max)))
        if rs.mileage_min:
            rows.append(('单次里程下限', '%.2f 公里' % rs.mileage_min))
        if rs.mileage_max:
            rows.append(('单次里程上限', '%.2f 公里' % rs.mileage_max))
        if rs.daily:
            rows.append(('每日配额', '%.2f 公里' % rs.daily))
        if rs.weekly:
            rows.append(('每周配额', '%.2f 公里' % rs.weekly))
        if rs.semester:
            rows.append(('学期配额', '%.2f 公里' % rs.semester))
        if rs.fixed_number:
            rows.append(('打卡点数量', str(rs.fixed_number)))
        rows.append(('打卡点坐标', '%d 个' % len(rs.sign_points)))
        rows.append(('围栏', '%d 个区域' % len(rs.fence)))

        self.tbl_rules.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.tbl_rules.setItem(i, 0, QTableWidgetItem(k))
            it = QTableWidgetItem(v)
            it.setForeground(QColor(C['accent2']))
            self.tbl_rules.setItem(i, 1, it)

        # 摘要
        bits = []
        if rs.pace_min and rs.pace_max:
            lo, hi = sorted([rs.pace_min, rs.pace_max])
            bits.append('配速 %d~%d' % (lo, hi))
        if rs.mileage_max:
            bits.append('单次≤%.1fkm' % rs.mileage_max)
        if rs.daily:
            bits.append('每日≤%.1fkm' % rs.daily)
        if rs.fixed_number:
            bits.append('%d个打卡点' % rs.fixed_number)
        if bits:
            self.lb_rule_summary.setText('✅ 规则已加载\n' + ' · '.join(bits))
        else:
            self.lb_rule_summary.setText('✅ 规则已加载（无限制项）')

        # 地图上画围栏和打卡点
        if rs.fence:
            self.map.set_fences(rs.fence)
        if rs.sign_points:
            self.map.set_sign_points(rs.sign_points)

    # ------------------------------------------------------------------
    def _start_timers(self):
        self.t_status = QTimer(self)
        self.t_status.timeout.connect(self._tick_status)
        self.t_status.start(1000)

    def _tick_status(self):
        if self.sched.running:
            self.pill_sched.set_text('调度运行中', 'ok')
            self.lb_next.setText('下次: ' + (self.sched.next_desc or '--'))
            self.lb_sched_state.setText(
                '运行中\n下次触发: %s\n上次触发: %s'
                % (self.sched.next_desc or '--',
                   self.sched.last_fire.strftime('%m-%d %H:%M')
                   if self.sched.last_fire else '无'))
        else:
            self.pill_sched.set_text('调度停止', 'idle')
            self.lb_next.setText('')
            self.lb_sched_state.setText('未启动')

        self._refresh_log()

        # 每 5 秒刷一次历史与配额
        self._tick_n = getattr(self, '_tick_n', 0) + 1
        if self._tick_n % 5 == 0:
            try:
                self._refresh_history()
            except Exception:
                pass

    def _refresh_log(self):
        lines = self.svc.log.recent(300)
        if not lines:
            return
        cur = self.txt_log.toPlainText()
        if len(lines) > 0:
            txt = '\n'.join(lines)
            if txt != cur:
                self.txt_log.setPlainText(txt)
                sb = self.txt_log.verticalScrollBar()
                sb.setValue(sb.maximum())

    # ------------------------------------------------------------------
    # 地图事件
    # ------------------------------------------------------------------
    def _on_map_ready(self):
        self.svc.log.info('地图就绪')
        # 范围跑核心：启动即加载学校围栏并自动生成内部跑道（先于登录）
        self._load_demo_fence()

    def _on_map_click(self, lat, lon):
        self.waypoints.append([lat, lon])
        self.map.set_points(self.waypoints)
        self._update_path_label()

    def _on_map_delete(self, idx):
        if 0 <= idx < len(self.waypoints):
            self.waypoints.pop(idx)
            self.map.set_points(self.waypoints)
            self._update_path_label()

    def _on_path_changed(self, pts, length, closed):
        # 主动设置闭合状态时，JS 的回调不要覆盖 Python 侧状态
        if getattr(self, '_suppress_path_sync', False):
            if pts and len(pts) != len(self.waypoints):
                self.waypoints = pts
            return
        if pts and len(pts) != len(self.waypoints):
            self.waypoints = pts
        self.closed = closed
        self._update_path_label(length)

    def _on_mouse_move(self, lat, lon, z):
        self.lb_coord.setText('%.6f, %.6f  z%d' % (lat, lon, z))

    def _update_path_label(self, length=None):
        n = len(self.waypoints)
        if n == 0:
            self.lb_path.setText('未绘制')
            return
        if length is None:
            length = 0.0
            import run_sim
            for i in range(n):
                a = self.waypoints[i]
                b = self.waypoints[(i + 1) % n]
                if i == n - 1 and not self.closed:
                    break
                length += run_sim.haversine(a[0], a[1], b[0], b[1])
        self.lb_path.setText('%d 点 · %.0f 米%s'
                             % (n, length, ' · 已闭合' if self.closed else ''))

    def _toggle_close(self):
        if len(self.waypoints) < 3:
            toast(self, '至少需要 3 个点')
            return
        self.closed = not self.closed
        # 抑制 JS 回调覆盖状态
        self._suppress_path_sync = True
        self.map.set_closed(self.closed)
        QTimer.singleShot(120, self._release_sync)
        self._update_path_label()
        toast(self, '已闭合跑道' if self.closed else '已取消闭合')

    def _release_sync(self):
        self._suppress_path_sync = False

    def _undo_point(self):
        if self.waypoints:
            self.waypoints.pop()
            self.map.set_points(self.waypoints)
            self._update_path_label()

    def _clear_path(self):
        self.waypoints = []
        self.closed = False
        self.map.clear_points()
        self.map.set_run_track([])
        self.map.set_position(None, None)
        self._update_path_label()

    def _goto_school(self):
        c = self.cfg.get('map_center') or [39.9042, 116.4074]
        self.map.goto(c[0], c[1], self.cfg.get('map_zoom') or 17)
        toast(self, '已定位到 %s' % (self.svc.session.school_name or '默认位置'))

    # ==================================================================
    # 范围跑核心：围栏加载 + 内部跑道自动生成
    # ==================================================================
    def _demo_fence_path(self):
        """当前学期 hasRule=false 时，用历史雅安围栏作为演示/默认围栏。"""
        return os.path.join(CFG.DATA_DIR, 'range_2024-2025_1.json')

    def _load_demo_fence(self):
        """地图就绪后：绘制学校范围 + 内部打卡点，并自动生成一条合规跑道。"""
        fence_path = self._demo_fence_path()
        if not os.path.exists(fence_path):
            self.svc.log.warning('未找到演示围栏数据: %s', fence_path)
            return
        try:
            d = CFG.load_json(fence_path, {})
            rs = R.RuleSet(d)
        except Exception as e:
            self.svc.log.warning('围栏解析失败: %s', e)
            return

        self.demo_rules = rs
        # 让体检/type 判定真正用上围栏规则（范围跑是核心产品）
        try:
            if self.svc.ruleset is None:
                self.svc.ruleset = rs
        except Exception:
            pass

        # 1) 绘制学校规定范围（红虚线）
        if rs.fence:
            self.map.set_fences(rs.fence)
        # 2) 绘制规定打卡点（当前演示数据无打卡点）
        if rs.sign_points:
            self.map.set_sign_points(rs.sign_points[:3])

        # 3) 自动定位到围栏质心
        c = self.cfg.get('map_center') or [29.980193, 102.995812]
        z = self.cfg.get('map_zoom') or 16
        self.map.goto(c[0], c[1], z)

        # 4) 自动生成一条落在围栏内部的跑道
        self._gen_from_fence(silent=True)

    def _gen_from_fence(self, silent=False):
        """用学校围栏生成一个全在内部的环形跑道，写入 self.waypoints。"""
        rs = getattr(self, 'demo_rules', None)
        if not rs or not rs.fence:
            if not silent:
                QMessageBox.information(self, '提示', '还没有可用的学校围栏')
            return
        poly = max(rs.fence, key=len)  # 取点最多的多边形
        loop = self._inset_loop(poly, inset_m=25.0)
        if len(loop) < 4:
            if not silent:
                QMessageBox.warning(self, '提示', '围栏太小，无法生成内部跑道')
            return

        # 用和 _toggle_close 相同的方式写回地图，避免 JS→Python 回环
        self.waypoints = [[lat, lon] for lat, lon in loop]
        self.closed = True
        self._suppress_path_sync = True
        self.map.set_points(self.waypoints)
        self.map.set_closed(self.closed)
        QTimer.singleShot(120, self._release_sync)
        self._update_path_label()
        if not silent:
            toast(self, '已按围栏生成内部跑道（%.0f 米）'
                  % (self._loop_len(self.waypoints)))

    @staticmethod
    def _nearest_foot(p, poly):
        """点 p 到多边形各边的最近垂足（lat,lon）。"""
        best = None
        for i in range(len(poly)):
            a = poly[i]
            b = poly[(i + 1) % len(poly)]
            ay, ax = a
            by, bx = b
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0:
                q = (ay, ax)
            else:
                t = ((p[1] - ax) * dx + (p[0] - ay) * dy) / (dx * dx + dy * dy)
                t = max(0.0, min(1.0, t))
                q = (ay + t * dy, ax + t * dx)
            dd = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
            if best is None or dd < best[0]:
                best = (dd, q)
        return best[1]

    @staticmethod
    def _inset_loop(poly, inset_m=15.0, step_m=50.0, eps_m=6.0):
        """在多边形内部生成一条贴近边界的环形跑道（所有顶点在范围内）。

        旧版只偏移 9 个稀疏顶点：稀疏顶点之间的**直线段**会横穿凹形
        围栏的颈部/凹口，导致 80% 采样点落在围栏外（范围跑要求 ≥30% 在内）。
        新版三步：
          1) 沿原始边界稠密采样（每 step_m 米一点，记录所属边）；
          2) 每个采样点沿所属边内法线内缩（深度试探 inset→…→0.7m，
             两侧方向都试过，保证落进内部；颈窄处自动变浅）；
          3) 闭合 Douglas-Peucker 简化回稀疏顶点（弦偏离真实内圈 ≤eps_m）。
        最后逐点兜底：仍偏出的点向最近边垂足二分收拢。
        """
        m = 111320.0
        fences = [poly]
        n = len(poly)

        def inside(p):
            return R.point_in_fences(p[0], p[1], fences)

        def inward(i, pt, depth):
            """沿第 i 边法线方向偏移 depth 米，返回落在内部的一侧。"""
            a = poly[i]
            b = poly[(i + 1) % n]
            dx = b[1] - a[1]
            dy = b[0] - a[0]
            L = math.hypot(dx, dy) or 1e-9
            ux, uy = dx / L, dy / L
            coslat = math.cos(math.radians(pt[1])) or 1e-9
            for s in (1.0, -1.0):
                q = (pt[0] + s * (depth / m) * uy,
                     pt[1] + s * (depth / (m * coslat)) * ux)
                if inside(q):
                    return q
            return None

        # 1) 沿原始边界稠密采样
        dense = []
        for i in range(n):
            a = poly[i]
            b = poly[(i + 1) % n]
            seg = RUNSIM.haversine(a[0], a[1], b[0], b[1])
            k = max(1, int(round(seg / step_m)))
            for j in range(k):
                f = j / float(k)
                dense.append(((a[0] + (b[0] - a[0]) * f,
                               a[1] + (b[1] - a[1]) * f), i))

        # 2) 逐点内缩（深度试探）
        depths = [inset_m, inset_m * 0.5, inset_m * 0.3,
                  inset_m * 0.15, 3.0, 1.0]
        ring = []
        for pt, i in dense:
            got = None
            for d in depths:
                got = inward(i, pt, d)
                if got:
                    break
            if got is None:
                # 极端窄颈：退回原边界点（最终兜底会收拢它）
                got = pt
            ring.append(got)

        # 3) 闭合 Douglas-Peucker 简化：在最远两点处断开成两段弧
        if len(ring) > 6:
            far = max(range(len(ring)),
                      key=lambda a: RUNSIM.haversine(
                          ring[a][0], ring[a][1],
                          ring[0][0], ring[0][1]))
            simp = MainWindow._dp_closed(ring, far, eps_m, m)
        else:
            simp = ring

        # 4) 兜底：简化后的弦可能局部外凸，逐点检查并收拢
        out = []
        for p in simp:
            if inside(p):
                out.append(p)
                continue
            q = MainWindow._nearest_foot(p, poly)
            dlat = q[0] - p[0]
            dlon = q[1] - p[1]
            lo, hi = 0.0, 1.0
            found = False
            for _ in range(40):
                mid = (lo + hi) / 2.0
                t = (p[0] + dlat * mid, p[1] + dlon * mid)
                if inside(t):
                    lo = mid
                    found = True
                else:
                    hi = mid
            out.append((p[0] + dlat * lo, p[1] + dlon * lo)
                       if found else MainWindow._nearest_foot(poly[0], poly))
        return out

    @staticmethod
    def _dp_closed(ring, cut, eps_m, m=111320.0):
        """在 ring[0] 与 ring[cut] 处断开，对两条弧分别做 DP 简化。"""
        def dp(pts):
            if len(pts) < 3:
                return pts
            a, b = pts[0], pts[-1]
            dmax, imax = -1.0, 0
            for i in range(1, len(pts) - 1):
                d = R._point_seg_dist(pts[i][0], pts[i][1], a, b)
                if d > dmax:
                    dmax, imax = d, i
            if dmax > eps_m:
                left = dp(pts[:imax + 1])
                right = dp(pts[imax:])
                return left[:-1] + right
            return [a, b]
        arc1 = dp(ring[:cut + 1])
        arc2 = dp(ring[cut:] + [ring[0]])
        return arc1[:-1] + arc2[:-1]

    @staticmethod
    def _loop_len(pts):
        n = len(pts)
        if n < 2:
            return 0.0
        return sum(RUNSIM.haversine(pts[i][0], pts[i][1],
                                    pts[(i + 1) % n][0], pts[(i + 1) % n][1])
                   for i in range(n))

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    def _do_login(self):
        phone = self.ed_phone.text().strip()
        pw = self.ed_pass.text()
        if not phone or not pw:
            QMessageBox.warning(self, '提示', '请填写手机号和密码')
            return

        self._collect_params()

        # 签名只影响「上传」，登录不校验。以后任何需要签名的操作
        # 会在自己的线程池里带看门狗检测，主线程永不被卡。
        self.btn_login.setEnabled(False)
        self.btn_login.setText('登录中…')
        self.pill_account.set_text('登录中', 'run')
        self.lb_status.setText('正在登录…')

        def done(ok, msg):
            self._post_ui(lambda: self._on_login_done(ok, msg))

        self.svc.login(phone, pw, on_done=done,
                       on_log=lambda m: self._post_ui(
                           lambda: self.lb_status.setText(m)))

    def _on_login_done(self, ok, msg):
        self.btn_login.setEnabled(True)
        self.btn_login.setText('登录')
        if ok:
            self._update_account_ui()
            self.pill_account.set_text(
                self.svc.session.real_name or '已登录', 'ok')
            self.lb_status.setText('登录成功')
            toast(self, '登录成功')
            # 自动拉规则
            if self.cfg.get('check_rules'):
                QTimer.singleShot(500, self._do_fetch_rules)
        else:
            self.pill_account.set_text('登录失败', 'err')
            self.lb_status.setText('登录失败: ' + msg)
            self._show_login_error(msg)

    def _show_login_error(self, msg):
        """登录失败时给出针对性诊断。"""
        hint = ''
        low = (msg or '').lower()
        if 'hs' in low or '签名' in msg or 'sign' in low:
            hint = ('\n\n【诊断】签名计算失败。\n'
                    'Frida 是否还连着？手机 App 是否还开着？')
        elif '密码' in msg or 'password' in low or '账号' in msg:
            hint = ('\n\n【诊断】账号或密码错误。\n'
                    '请确认用的是乐健体育 App 的登录密码，\n'
                    '不是学校教务系统的密码。')
        elif 'token' in low:
            hint = ('\n\n【诊断】服务端没返回 token。\n'
                    '可能是接口变更，或账号被限制。')
        elif 'timeout' in low or 'connect' in low or '网络' in msg:
            hint = ('\n\n【诊断】网络问题。\n'
                    '检查能否访问 cpes.legym.cn。')
        else:
            hint = ('\n\n【排查建议】\n'
                    '1. 确认签名配置正确（点「签名」旁的 ?）\n'
                    '2. 确认账号密码是乐健 App 的\n'
                    '3. 看「日志」页的详细错误')

        QMessageBox.warning(self, '登录失败', msg + hint)

    def _do_fetch_rules(self):
        if not self.svc.session.valid:
            QMessageBox.warning(self, '提示', '请先登录')
            return
        c = self.cfg.get('map_center') or [39.9042, 116.4074]
        self.btn_refresh_rules.setEnabled(False)
        self.pill_rules.set_text('拉取中', 'run')

        def done(ok, data):
            self._post_ui(lambda: self._on_rules_done(ok))

        self.svc.fetch_rules(c[0], c[1], on_done=done)

    def _on_rules_done(self, ok):
        self.btn_refresh_rules.setEnabled(True)
        if ok and self.svc.ruleset:
            self._render_rules(self.svc.ruleset)
            self.pill_rules.set_text('规则已加载', 'ok')
            toast(self, '规则已加载')
            self._auto_fill()
        else:
            self.pill_rules.set_text('规则失败', 'err')
            toast(self, '拉取规则失败')

    def _auto_fill(self):
        rs = self.svc.ruleset
        if not rs:
            toast(self, '请先加载规则')
            return
        sug = rs.suggest()
        self.sp_pace.setValue(int(sug['pace']))
        self.sp_duration.setValue(int(sug['duration']))
        toast(self, '已按规则填: 配速 %d 秒/公里, 时长 %d 秒'
              % (sug['pace'], sug['duration']))

    def _randomize(self):
        import random
        base = self.sp_pace.value()
        self.sp_pace.setValue(int(base * random.uniform(0.92, 1.08)))
        base = self.sp_duration.value()
        self.sp_duration.setValue(int(base * random.uniform(0.9, 1.1)))
        toast(self, '参数已随机化')

    def _collect_params(self):
        self.cfg.set('pace', self.sp_pace.value())
        self.cfg.set('duration', self.sp_duration.value())
        self.cfg.set('noise', self.sp_noise.value())
        self.cfg.set('drop', self.sp_drop.value())
        self.cfg.set('sign_mode',
                     ['all', 'alt', 'none'][self.cb_sign.currentIndex()])
        self.cfg.set('hs_mode',
                     'frida' if self.cb_hs.currentIndex() == 0 else 'table')
        self.cfg.set('frida_host', self.ed_frida.text())
        self.cfg.set('hs_table', self.ed_hstable.text())
        self.cfg.set('semester_id', self.ed_semester.text())
        self.cfg.set('lgs_id', self.ed_lgs.text())
        self.cfg.set('school_id', self.ed_school.text())
        self.cfg.set('check_rules', self.cb_check.isChecked())
        self.cfg.set('force_upload', self.cb_force.isChecked())
        self.cfg.set('max_daily_km', self.sp_daily.value())
        self.cfg.set('min_interval_hours', self.sp_interval.value())
        self.cfg.set('tray_on_close', self.cb_tray.isChecked())
        self.cfg.save()

    def _do_preview(self):
        if len(self.waypoints) < 3:
            QMessageBox.warning(self, '提示',
                                '请先在地图上画出跑道（至少 3 个点）')
            return
        self._collect_params()
        self.btn_preview.setEnabled(False)
        self.lb_status.setText('生成轨迹…')

        try:
            vo, pts, st = self.svc.build_track(self.waypoints)
            self.last_vo = vo
            self.last_stats = st
            self.run_points = [(p[1], p[2]) for p in pts]

            self.map.set_run_track(self.run_points)
            if self.run_points:
                self.map.set_position(*self.run_points[0], text='起点')

            ok, probs, warns = self.svc.check(vo)
            self.lb_live_dist.setText(
                '里程 %.2f km · 时长 %d s · 采样 %d 点'
                % (st['mileage_m'] / 1000, st['keep_s'], st['points']))
            self.lb_live_pace.setText('%.0f' % st['pace'])

            if probs:
                self.lb_status.setText('体检问题: ' + probs[0])
                QMessageBox.warning(
                    self, '体检未通过',
                    '发现以下问题：\n\n' + '\n'.join('· ' + p for p in probs)
                    + '\n\n可以点「按规则自动填」重新生成。')
            else:
                self.lb_status.setText('预览就绪，体检通过')
                toast(self, '✓ 轨迹已生成，体检通过')

            # 播放一遍轨迹动画预览
            self._animate_track(preview=True)
        except ValueError as e:
            self.lb_status.setText('生成失败: %s' % e)
            QMessageBox.warning(
                self, '跑道有问题',
                str(e) + '\n\n【怎么画】\n'
                '· 在地图上沿操场边缘点 4~8 个点\n'
                '· 相邻点之间至少隔 10 米\n'
                '· 画完点「闭合跑道」')
        except Exception as e:
            self.lb_status.setText('生成失败: %s' % e)
            QMessageBox.critical(
                self, '生成失败',
                '%s\n\n请检查：\n'
                '· 跑道是否闭合\n'
                '· 配速和时长是否合理\n'
                '· 看「日志」页有无更多信息' % e)
        finally:
            self.btn_preview.setEnabled(True)

    def _refresh_upload_ready(self):
        try:
            ready = self.svc.upload_ready()
        except Exception:
            ready = False
        if ready:
            self.lb_upload_ready.setText(
                '✅ 上传已校准（使用真机抓包结构）')
            self.lb_upload_ready.setStyleSheet(
                'color:%s;background:#1e3a24;border:1px solid #2d5a38;'
                'border-radius:5px;padding:6px;font-size:11px;' % C['accent2'])
        else:
            self.lb_upload_ready.setText(
                '⚠ 上传未校准：需先用 capture_run.py 抓一次真机上传\n'
                '（登录/规则/轨迹生成都正常，只有"开始刷"需要此步）')
            self.lb_upload_ready.setStyleSheet(
                'color:%s;background:#3a321e;border:1px solid #5a4d2d;'
                'border-radius:5px;padding:6px;font-size:11px;' % C['warn'])

    def _show_capture_help(self):
        from widgets import HelpDialog
        HelpDialog(
            '上传校准（一次性）',
            '为什么要校准：\n'
            '实测发现上传接口 v3/upload 的请求体结构和登录不同，'
            '静态无法确定服务端 DTO 的确切字段形态，'
            '盲发会被判「参数为 null」。\n\n'
            '怎么做（只需一次）：\n'
            '1. 手机开 USB 调试并连电脑（root + frida-server）\n'
            '2. 电脑上执行：\n'
            '   python capture_run.py\n'
            '3. 脚本自动启动乐健 App，你在手机上自由跑 200~400 米\n'
            '4. 到点结束跑步，让 App 正常上传\n'
            '5. 看到 [saved] 后回来，本窗口会显示「已校准」\n\n'
            '之后所有上传都用真实结构回放，无需再抓。\n\n'
            '原理：capture_upload.js 钩住 kernel 加密入口 '
            'f.m.b.h.a.b()，在 AES 加密前截获明文 DTO。',
            self).exec()

    def _do_run(self):
        if len(self.waypoints) < 3:
            QMessageBox.warning(self, '提示',
                                '请先在地图上画出跑道（至少 3 个点）')
            return
        if not self.svc.session.valid:
            QMessageBox.warning(self, '提示', '请先登录')
            return

        self._collect_params()
        self.btn_run.setEnabled(False)
        self.btn_run.setText('执行中…')
        self.prog.setValue(5)
        self.lb_status.setText('执行中…')

        def progress(stage, msg):
            self._post_ui(lambda: self._on_run_progress(stage, msg))

        def done(ok, msg, vo, pts, st):
            self._post_ui(lambda: self._on_run_done(ok, msg, vo, pts, st))

        self.svc.run_once(self.waypoints, on_progress=progress, on_done=done)

    def _on_run_progress(self, stage, msg):
        self.lb_status.setText('[%s] %s' % (stage, msg))
        if stage == '生成':
            self.prog.setValue(30)
        elif stage == '体检':
            self.prog.setValue(55)
        elif stage == '上传':
            self.prog.setValue(80)

    def _on_run_done(self, ok, msg, vo, pts, st):
        self.btn_run.setEnabled(True)
        self.btn_run.setText('开始刷')
        self.prog.setValue(100 if ok else 0)
        self._refresh_history()
        if ok:
            self.lb_status.setText('✓ 上传成功')
            toast(self, '✓ 上传成功')
            self._animate_track()
        else:
            self.lb_status.setText('✗ ' + msg)
            self._show_run_error(msg)

    def _show_run_error(self, msg):
        """执行失败时给出针对性诊断。"""
        hint = ''
        low = (msg or '').lower()
        if '配额' in msg or '上限' in msg or '间隔' in msg:
            hint = ('\n\n【这是本地保护】\n'
                    '为防止异常行为，程序限制了每日里程和最小间隔。\n'
                    '可在「定时」页调整，或勾选「强制上传」跳过。')
        elif '体检' in msg:
            hint = ('\n\n【怎么修】\n'
                    '点「按规则自动填」重新生成参数，\n'
                    '或在地图上调整跑道让轨迹落在围栏内。')
        elif 'token' in low or '未登录' in msg:
            hint = '\n\n【怎么修】\n请先在账号页登录。'
        elif 'hs' in low or '签名' in msg:
            hint = ('\n\n【怎么修】\n'
                    '检查签名配置：Frida 是否连着、App 是否开着。\n'
                    '点「检查签名是否可用」验证。')
        else:
            hint = '\n\n详情看「日志」页。'

        QMessageBox.warning(self, '执行失败', msg + hint)

    def _animate_track(self, preview=False):
        """播放轨迹动画，模拟跑步过程，实时显示位置和配速。"""
        if not self.run_points:
            return
        self._run_anim_idx = 0
        self._anim_preview = preview
        self._anim_t0 = time.time()
        if self._anim_timer:
            self._anim_timer.stop()

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._anim_step)
        self._anim_timer.start(60)

    def _anim_step(self):
        if self._run_anim_idx >= len(self.run_points):
            self._anim_timer.stop()
            self._anim_timer = None
            self.lb_live_pace.setText('完成')
            self.lb_live_pos.setText('轨迹播放完毕')
            self.prog.setValue(100)
            return

        n = len(self.run_points)
        i = min(self._run_anim_idx, n - 1)
        lat, lon = self.run_points[i]

        # 配速随时间自然波动（复刻真实跑步）
        import math
        t = (time.time() - getattr(self, '_anim_t0', time.time()))
        base_pace = 340.0
        if self.last_stats:
            base_pace = self.last_stats.get('pace') or 340.0
        # 呼吸 + 疲劳 + 抖动
        wave = (1.0 + 0.035 * math.sin(t * 3.8)
                + 0.02 * math.sin(t * 11.3)
                + 0.03 * (i / max(1, n)))      # 后半程略慢
        pace = base_pace * wave
        speed = 1000.0 / pace if pace else 0

        self.map.set_position(lat, lon, text='%.1f km/h' % (speed * 3.6))
        self.lb_live_pos.setText('位置 %.6f, %.6f' % (lat, lon))
        self.lb_live_pace.setText('%.0f' % pace)
        self.prog.setValue(int(i / max(1, n) * 100))

        # 每帧推进，让动画约 12 秒播完
        step = max(1, n // 200)
        self._run_anim_idx += step

    # ------------------------------------------------------------------
    def _on_hs_changed(self, i):
        is_frida = (i == 0)
        self.ed_frida.setEnabled(is_frida)
        self.ed_hstable.setEnabled(not is_frida)
        self.lb_hs_state.setText('未检查')

    def _do_check_hs(self):
        self._collect_params()
        self.btn_check_hs.setEnabled(False)
        self.btn_check_hs.setText('检查中…')
        self.lb_hs_state.setText('检查中…')

        def worker():
            ok, msg = self.svc.check_hs_ready()
            self._post_ui(lambda: self._on_check_hs_done(ok, msg))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_check_hs_done(self, ok, msg):
        self.btn_check_hs.setEnabled(True)
        self.btn_check_hs.setText('检查签名是否可用')
        self.lb_hs_state.setText(('✓ ' if ok else '✗ ') + msg)
        self.lb_hs_state.setStyleSheet(
            'color:%s;background:%s;border:1px solid %s;'
            'border-radius:5px;padding:6px;font-size:11px;'
            % (C['accent2'] if ok else C['err'],
               C['bg2'],
               '#2d5a38' if ok else '#5a2d2d'))
        if ok:
            self.svc.reset_hs()

    # ------------------------------------------------------------------
    def _add_time(self):
        t = self.te_new.time().toString('HH:mm')
        if not self.lst_times.findItems(t, Qt.MatchFlag.MatchExactly):
            self.lst_times.addItem(t)
            self._save_times()

    def _del_time(self):
        r = self.lst_times.currentRow()
        if r >= 0:
            self.lst_times.takeItem(r)
            self._save_times()

    def _save_times(self):
        times = [self.lst_times.item(i).text()
                 for i in range(self.lst_times.count())]
        self.cfg.set('schedule_times', times)
        self.cfg.save()

    def _on_sched_toggle(self, v):
        self.cfg.set('schedule_enabled', v)
        self.cfg.save()

    def _start_sched(self):
        self._collect_params()
        days = [i + 1 for i, cb in enumerate(self.day_checks) if cb.isChecked()]
        self.cfg.set('schedule_days', days)
        self.cfg.set('schedule_jitter_min', self.sp_jitter.value())
        self._save_times()
        self.cfg.save()

        if not days:
            QMessageBox.warning(self, '提示', '至少选一个执行星期')
            return
        if self.lst_times.count() == 0:
            QMessageBox.warning(self, '提示', '至少添加一个时间点')
            return

        self.sched.start()
        toast(self, '定时任务已启动')

    def _stop_sched(self):
        self.sched.stop()
        toast(self, '定时任务已停止')

    def _on_schedule_fire(self):
        # 调度器线程触发：先 marshal 回主线程再读状态/操作控件
        self._post_ui(self._schedule_fire_ui)

    def _schedule_fire_ui(self):
        if len(self.waypoints) < 3:
            self.svc.log.warn('定时触发但未绘制跑道，跳过')
            return
        if not self.svc.session.valid:
            self.svc.log.warn('定时触发但未登录，跳过')
            return
        self.svc.log.info('定时任务开始执行')

        def done(ok, msg, vo, pts, st):
            # service worker 线程回调：先回主线程（_animate_track 操作控件）
            def apply():
                if ok:
                    self.svc.log.ok('定时任务完成')
                    self._animate_track()
                else:
                    self.svc.log.error('定时任务失败: %s' % msg)
            self._post_ui(apply)

        self.svc.run_once(self.waypoints, on_done=done)

    # ------------------------------------------------------------------
    def _show_guide(self):
        QMessageBox.information(
            self, '使用说明',
            '【使用流程】\n\n'
            '1. 账号页：填手机号密码，点登录\n'
            '2. 登录后自动拉取学校规则\n'
            '3. 地图上沿操场点一圈（4~8 个点）\n'
            '4. 点「闭合跑道」\n'
            '5. 刷步页：点「按规则自动填」\n'
            '6. 点「预览轨迹」确认无误\n'
            '7. 点「开始刷」\n\n'
            '【定时】\n'
            '定时页设置时间点，启动调度后\n'
            '关窗口会最小化到托盘继续运行。\n\n'
            '【安全建议】\n'
            '· 每天 1~2 次，间隔 8 小时以上\n'
            '· 保持「上传前体检」开启\n'
            '· 参数别固定，用「随机变化」\n\n'
            '任何选项旁边的 ? 都能点开看说明。')

    def _export_log(self):
        p, _ = QFileDialog.getSaveFileName(self, '导出日志', 'happyfuck.log',
                                           'Log (*.log *.txt)')
        if p:
            try:
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(self.txt_log.toPlainText())
                toast(self, '已导出')
            except Exception as e:
                QMessageBox.warning(self, '导出失败', str(e))

    def _open_data_dir(self):
        import subprocess
        try:
            if sys.platform == 'win32':
                os.startfile(CFG.DATA_DIR)
            else:
                subprocess.Popen(['xdg-open', CFG.DATA_DIR])
        except Exception as e:
            QMessageBox.warning(self, '打开失败', str(e))

    def _reset_config(self):
        r = QMessageBox.question(self, '确认', '重置所有配置？此操作不可撤销。')
        if r == QMessageBox.StandardButton.Yes:
            try:
                os.remove(CFG.CONFIG_FILE)
            except Exception:
                pass
            QMessageBox.information(self, '完成', '配置已重置，请重启程序')

    # ------------------------------------------------------------------
    def closeEvent(self, e):
        self._collect_params()
        if self.cb_tray.isChecked() and self.sched.running:
            e.ignore()
            self.hide()
            self.svc.log.info('已最小化到托盘，定时任务继续运行')
            return
        self.sched.stop()
        try:
            self.map.shutdown()
        except Exception:
            pass
        e.accept()
