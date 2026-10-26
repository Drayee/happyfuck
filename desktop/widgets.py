#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 通用 UI 组件：带 ? 提示的控件。"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QToolButton,
                             QToolTip, QFrame, QVBoxLayout, QSizePolicy,
                             QDialog, QPushButton, QTextBrowser)

from theme import C


class HelpDialog(QDialog):
    """帮助说明弹窗（比 tooltip 更适合长文本）。"""

    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle('说明 · %s' % title)
        self.setMinimumSize(460, 320)
        self.resize(520, 400)
        self.setStyleSheet(
            'QDialog{background:%s;}'
            'QTextBrowser{background:%s;color:%s;border:1px solid %s;'
            'border-radius:6px;padding:10px;font-size:13px;}'
            'QPushButton{background:%s;color:#fff;border:none;'
            'border-radius:6px;padding:8px 24px;font-weight:bold;}'
            'QPushButton:hover{background:#6db3ff;}'
            % (C['bg1'], C['bg2'], C['fg'], C['border'], C['accent']))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        head = QLabel(title)
        head.setStyleSheet('color:%s;font:bold 15px "Microsoft YaHei";'
                           % C['accent'])
        lay.addWidget(head)

        body = QTextBrowser()
        body.setOpenExternalLinks(False)
        body.setHtml(self._render(text or ''))
        lay.addWidget(body, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton('知道了')
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        lay.addLayout(row)

    @staticmethod
    def _render(text):
        """把纯文本转成带样式的 HTML。"""
        if not text:
            return '<p style="color:#8b98a8">（暂无说明）</p>'
        lines = []
        for raw in str(text).split('\n'):
            line = raw.rstrip()
            if not line:
                lines.append('<div style="height:8px"></div>')
            elif line.startswith('【') or line.startswith('['):
                lines.append(
                    '<p style="color:%s;font-weight:bold;margin:8px 0 4px 0">'
                    '%s</p>' % (C['accent2'], _esc(line)))
            elif line.startswith('·') or line.startswith('-'):
                lines.append(
                    '<p style="margin:2px 0 2px 12px;color:%s">%s</p>'
                    % (C['fg'], _esc(line)))
            elif line.startswith('⚠') or line.startswith('!!'):
                lines.append(
                    '<p style="color:%s;margin:4px 0">%s</p>'
                    % (C['warn'], _esc(line)))
            else:
                lines.append('<p style="margin:4px 0;color:%s">%s</p>'
                             % (C['fg'], _esc(line)))
        return ''.join(lines)


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


class HelpButton(QToolButton):
    """? 按钮，点击弹出说明窗口。"""

    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setText('?')
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self._title = title or ''
        self._text = text or ''
        self.setToolTip('点击查看说明')
        self.setStyleSheet(
            'QToolButton{background:%s;color:%s;border:1px solid %s;'
            'border-radius:9px;font:bold 11px "Segoe UI";}'
            'QToolButton:hover{background:%s;color:#fff;}'
            % (C['bg3'], C['fg_dim'], C['border'], C['accent']))
        self.clicked.connect(self._show)

    def _show(self):
        try:
            dlg = HelpDialog(self._title, self._text, self.window())
            dlg.exec()
        except Exception as e:
            # 极端情况下退化为 tooltip
            try:
                QToolTip.showText(
                    self.mapToGlobal(self.rect().bottomLeft()),
                    '%s\n\n%s' % (self._title, self._text), self)
            except Exception:
                print('[help] failed:', e)


class LabeledRow(QWidget):
    """一行：标签 + ? + 控件。"""

    def __init__(self, label, widget, help_title=None, help_text=None,
                 label_width=110, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        lb = QLabel(label)
        lb.setFixedWidth(label_width)
        lb.setStyleSheet('color:%s;' % C['fg_dim'])
        lay.addWidget(lb)

        if help_text:
            lay.addWidget(HelpButton(help_title or label, help_text))

        lay.addWidget(widget, 1)


class SectionTitle(QWidget):
    """分组标题 + 说明。"""

    def __init__(self, text, help_title=None, help_text=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 4)
        lay.setSpacing(6)

        lb = QLabel(text)
        lb.setStyleSheet('color:%s;font:bold 12px "Microsoft YaHei";'
                         % C['accent'])
        lay.addWidget(lb)

        if help_text:
            lay.addWidget(HelpButton(help_title or text, help_text))

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('color:%s;' % C['border'])
        lay.addWidget(line, 1)


class StatusPill(QLabel):
    """状态徽标。"""

    def __init__(self, text='', kind='idle', parent=None):
        super().__init__(text, parent)
        self.set_kind(kind)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)

    def set_kind(self, kind):
        colors = {
            'idle': (C['bg3'], C['fg_dim'], C['border']),
            'ok': ('#1e3a24', '#5fd97a', '#2d5a38'),
            'warn': ('#3a321e', '#e8c05a', '#5a4d2d'),
            'err': ('#3a1e1e', '#ff6b6b', '#5a2d2d'),
            'run': ('#1e2d3a', '#4ea1ff', '#2d4a5a'),
        }
        bg, fg, bd = colors.get(kind, colors['idle'])
        self.setStyleSheet(
            'QLabel{background:%s;color:%s;border:1px solid %s;'
            'border-radius:11px;padding:2px 10px;font:11px "Microsoft YaHei";}'
            % (bg, fg, bd))

    def set_text(self, t, kind=None):
        self.setText(t)
        if kind:
            self.set_kind(kind)


def toast(parent, msg, ms=2500):
    """轻量提示。"""
    lb = QLabel(msg, parent)
    lb.setStyleSheet(
        'QLabel{background:%s;color:%s;border:1px solid %s;'
        'border-radius:6px;padding:8px 16px;font:12px "Microsoft YaHei";}'
        % (C['bg3'], C['fg'], C['accent']))
    lb.adjustSize()
    p = parent.rect().center()
    lb.move(p.x() - lb.width() // 2, p.y() - lb.height() // 2)
    lb.show()
    lb.raise_()
    QTimer.singleShot(ms, lb.deleteLater)
