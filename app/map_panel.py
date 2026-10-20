#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 地图面板（WebEngine + Leaflet + 本地瓦片代理）。"""
import json
import os
import sys

from PyQt6.QtCore import QUrl, QObject, pyqtSlot, pyqtSignal, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

import config as CFG
import tile_server


class _Bridge(QObject):
    ready = pyqtSignal()
    mapClicked = pyqtSignal(float, float)
    deleteRequested = pyqtSignal(int)
    pathChanged = pyqtSignal(list, float, bool)
    mouseMoved = pyqtSignal(float, float, int)

    @pyqtSlot()
    def onReady(self):
        self.ready.emit()

    @pyqtSlot(float, float)
    def onMapClick(self, la, lo):
        self.mapClicked.emit(la, lo)

    @pyqtSlot(int)
    def onDeleteRequest(self, i):
        self.deleteRequested.emit(i)

    @pyqtSlot(str, float, bool)
    def onPathChanged(self, js, length, closed):
        try:
            pts = json.loads(js) if js else []
        except Exception:
            pts = []
        self.pathChanged.emit(pts, length, closed)

    @pyqtSlot(float, float, int)
    def onMouseMove(self, la, lo, z):
        self.mouseMoved.emit(la, lo, z)


class MapPanel(QWidget):
    """地图控件封装。"""

    ready = pyqtSignal()
    mapClicked = pyqtSignal(float, float)
    deleteRequested = pyqtSignal(int)
    pathChanged = pyqtSignal(list, float, bool)
    mouseMoved = pyqtSignal(float, float, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.view = QWebEngineView()
        lay.addWidget(self.view)

        self._srv = None
        self._port = 0
        self._ready = False

        self.bridge = _Bridge()
        self.bridge.ready.connect(self._on_ready)
        self.bridge.mapClicked.connect(self.mapClicked)
        self.bridge.deleteRequested.connect(self.deleteRequested)
        self.bridge.pathChanged.connect(self.pathChanged)
        self.bridge.mouseMoved.connect(self.mouseMoved)

        # 必须保存引用，否则 QWebChannel 被 GC 后桥接失效
        self._channel = QWebChannel()
        self._channel.registerObject('bridge', self.bridge)
        self.view.page().setWebChannel(self._channel)

        self._start_server()

    # ------------------------------------------------------------------
    def _start_server(self):
        try:
            self._srv, self._port = tile_server.start(0)
            url = 'http://127.0.0.1:%d/map2.html' % self._port
            self.view.load(QUrl(url))
        except Exception as e:
            print('[map] server failed:', e)
            self.view.setHtml(
                '<body style="background:#131820;color:#ff6b6b;'
                'font:14px monospace;padding:20px">地图服务启动失败<br>%s</body>'
                % e)

    def _on_ready(self):
        self._ready = True
        self.ready.emit()
        # 恢复地图中心
        c = CFG.Config().get('map_center') or [39.9042, 116.4074]
        z = CFG.Config().get('map_zoom') or 17
        self.goto(c[0], c[1], z)

    # ------------------------------------------------------------------
    def js(self, code):
        if self._ready:
            self.view.page().runJavaScript(code)

    def goto(self, lat, lon, zoom=None):
        self.js('API.goto(%f,%f,%s);' % (lat, lon, zoom or 'null'))

    def set_points(self, pts):
        self.js('API.setPoints(%s);' % json.dumps(json.dumps(pts)))

    def clear_points(self):
        self.js('API.clearPoints();')

    def set_closed(self, v):
        self.js('API.setClosed(%s);' % ('true' if v else 'false'))

    def delete_point(self, i):
        self.js('API.deletePoint(%d);' % i)

    def set_fences(self, polys):
        """polys: [[[lat,lon],...], ...]"""
        self.js('setFences(%s);' % json.dumps(json.dumps(polys)))

    def set_sign_points(self, pts):
        self.js('setSignPoints(%s);' % json.dumps(json.dumps(pts)))

    def set_run_track(self, pts):
        self.js('setRunTrack(%s);' % json.dumps(json.dumps(pts)))

    def set_position(self, lat, lon, text='当前位置'):
        if lat is None:
            self.js('setPosition(null,null,null);')
        else:
            self.js('setPosition(%f,%f,%s);'
                    % (lat, lon, json.dumps(text)))

    def set_sat(self, on):
        self.js('API.setSat(%s);' % ('true' if on else 'false'))

    def get_center(self):
        return CFG.Config().get('map_center')

    def shutdown(self):
        if self._srv:
            try:
                self._srv.shutdown()
            except Exception:
                pass
            self._srv = None
