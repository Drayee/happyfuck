#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 深色主题。"""

C = {
    'bg0': '#0d1117',      # 最深
    'bg1': '#131820',      # 主背景
    'bg2': '#1a212b',      # 面板
    'bg3': '#232b36',      # 控件
    'bg4': '#2d3743',      # hover

    'fg': '#d6deeb',       # 主文字
    'fg_dim': '#8b98a8',   # 次要
    'fg_mute': '#5a6675',  # 更淡

    'accent': '#4ea1ff',   # 主色（蓝）
    'accent2': '#3ddc84',  # 成功（绿）
    'warn': '#e8c05a',     # 警告（黄）
    'err': '#ff6b6b',      # 错误（红）
    'purple': '#a78bfa',

    'border': '#2a3441',
}


def stylesheet():
    return """
* {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px;
}
QMainWindow, QDialog {
    background: %(bg1)s;
}
QWidget#SidePanel {
    background: %(bg2)s;
    border-left: 1px solid %(border)s;
}
QWidget#TopBar {
    background: %(bg0)s;
    border-bottom: 1px solid %(border)s;
}
QWidget#BottomBar {
    background: %(bg0)s;
    border-top: 1px solid %(border)s;
}

QLabel { color: %(fg)s; background: transparent; }
QLabel#Title { color: %(accent)s; font: bold 15px "Microsoft YaHei"; }
QLabel#Subtitle { color: %(fg_mute)s; font: 11px "Microsoft YaHei"; }

QPushButton {
    background: %(bg3)s;
    color: %(fg)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 7px 14px;
    min-height: 16px;
}
QPushButton:hover { background: %(bg4)s; border-color: %(accent)s; }
QPushButton:pressed { background: %(bg2)s; }
QPushButton:disabled { color: %(fg_mute)s; background: %(bg2)s; }

QPushButton#Primary {
    background: %(accent)s; color: #fff; border: none; font-weight: bold;
}
QPushButton#Primary:hover { background: #6db3ff; }
QPushButton#Primary:disabled { background: %(bg3)s; color: %(fg_mute)s; }

QPushButton#Success {
    background: #2d7a4a; color: #fff; border: none; font-weight: bold;
}
QPushButton#Success:hover { background: #369159; }
QPushButton#Success:disabled { background: %(bg3)s; color: %(fg_mute)s; }

QPushButton#Danger {
    background: #8b3a3a; color: #fff; border: none;
}
QPushButton#Danger:hover { background: #a34545; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background: %(bg3)s;
    color: %(fg)s;
    border: 1px solid %(border)s;
    border-radius: 5px;
    padding: 6px 8px;
    selection-background-color: %(accent)s;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QPlainTextEdit:focus {
    border-color: %(accent)s;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: %(fg_mute)s; background: %(bg2)s;
}

QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow {
    image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid %(fg_dim)s;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: %(bg3)s; color: %(fg)s;
    border: 1px solid %(accent)s;
    selection-background-color: %(accent)s;
    outline: none;
}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: %(bg4)s; border: none; width: 16px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    border-left: 3px solid transparent; border-right: 3px solid transparent;
    border-bottom: 4px solid %(fg_dim)s;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    border-left: 3px solid transparent; border-right: 3px solid transparent;
    border-top: 4px solid %(fg_dim)s;
}

QCheckBox, QRadioButton { color: %(fg)s; spacing: 6px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 15px; height: 15px;
    border: 1px solid %(border)s; background: %(bg3)s;
}
QCheckBox::indicator { border-radius: 3px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:checked {
    background: %(accent)s; border-color: %(accent)s;
}
QRadioButton::indicator:checked {
    background: %(accent)s; border-color: %(accent)s;
}

QTabWidget::pane {
    border: 1px solid %(border)s;
    background: %(bg1)s;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: %(bg2)s;
    color: %(fg_dim)s;
    border: 1px solid %(border)s;
    border-bottom: none;
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: %(bg1)s; color: %(accent)s; font-weight: bold;
}
QTabBar::tab:hover:!selected { background: %(bg3)s; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: %(bg1)s; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: %(bg4)s; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal {
    background: %(bg1)s; height: 10px;
}
QScrollBar::handle:horizontal {
    background: %(bg4)s; border-radius: 5px; min-width: 24px;
}

QGroupBox {
    border: 1px solid %(border)s;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    color: %(fg_dim)s;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px; padding: 0 4px;
    color: %(accent)s;
}

QTableWidget {
    background: %(bg2)s; color: %(fg)s;
    border: 1px solid %(border)s; border-radius: 6px;
    gridline-color: %(border)s;
}
QTableWidget::item { padding: 4px; }
QTableWidget::item:selected {
    background: %(accent)s; color: #fff;
}
QHeaderView::section {
    background: %(bg3)s; color: %(fg_dim)s;
    border: none; border-right: 1px solid %(border)s;
    border-bottom: 1px solid %(border)s;
    padding: 6px; font-weight: bold;
}

QMenu {
    background: %(bg3)s; color: %(fg)s;
    border: 1px solid %(border)s; border-radius: 6px; padding: 4px;
}
QMenu::item { padding: 6px 24px; border-radius: 4px; }
QMenu::item:selected { background: %(accent)s; color: #fff; }

QToolTip {
    background: %(bg3)s; color: %(fg)s;
    border: 1px solid %(accent)s; border-radius: 5px;
    padding: 6px; font-size: 12px;
}

QProgressBar {
    background: %(bg3)s; border: none; border-radius: 4px;
    height: 6px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }

QSplitter::handle { background: %(border)s; width: 1px; }
""" % C
