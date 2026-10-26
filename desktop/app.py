#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 程序入口。

用法:
    python app.py           正常启动
    python app.py --debug   带调试输出
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# QtWebEngine 必须在 QApplication 之前初始化
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS',
                      '--disable-gpu-sandbox --no-sandbox '
                      '--enable-features=NetworkService')
os.environ.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')

from PyQt6.QtCore import Qt, QTimer, QCoreApplication
# 必须在 QApplication 之前：共享 OpenGL 上下文
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from PyQt6.QtWebEngineCore import QWebEngineProfile  # noqa: F401

from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox

import theme as TH
import config as CFG


def make_icon():
    """程序化生成图标：圆角方块 + 乐字。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(TH.C['accent']))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor('#ffffff'))
    f = QFont('Microsoft YaHei', 30, QFont.Weight.Bold)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, '乐')
    p.end()
    return QIcon(pm)


def main():
    debug = '--debug' in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName(CFG.APP_NAME)
    app.setApplicationVersion(CFG.APP_VERSION)
    app.setStyleSheet(TH.stylesheet())

    icon = make_icon()
    app.setWindowIcon(icon)

    from main_window import MainWindow
    win = MainWindow()
    win.setWindowIcon(icon)

    # 托盘
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip('%s v%s' % (CFG.APP_NAME, CFG.APP_VERSION))

    menu = QMenu()
    act_show = QAction('显示主窗口', app)
    act_show.triggered.connect(lambda: (win.showNormal(), win.activateWindow()))
    menu.addAction(act_show)

    act_run = QAction('立即执行一次', app)
    act_run.triggered.connect(win._do_run)
    menu.addAction(act_run)

    menu.addSeparator()

    act_quit = QAction('退出', app)
    act_quit.triggered.connect(lambda: (win.sched.stop(), app.quit()))
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda r: (win.showNormal(), win.activateWindow())
        if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()

    win.show()

    if debug:
        print('[debug] data dir:', CFG.DATA_DIR)
        print('[debug] tools   :', CFG.TOOLS)
        print('[debug] python  :', sys.executable)

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
