"""本地 HTTP 服务器方案：提供地图页 + 代理高德瓦片。

比自定义 scheme 更稳，不依赖 Qt 的 scheme 权限机制。

健壮性（2026-10-20）：
- 浏览器（Leaflet）滚动地图时会批量中止屏外瓦片请求，属正常行为：
  写回阶段 BrokenPipe/ConnectionAborted 一律静默忽略，不再打 traceback。
- 上游偶发超时：自动换子域（webrd/webst 01~04）重试一次。
- 上游彻底失败：返回内存生成的 256x256 全透明 PNG 占位瓦片（HTTP 200），
  地图不白块、Leaflet 不重试风暴；并记 60s 负缓存，避免反复打挂起的主机。
"""
import os
import socket
import struct
import sys
import threading
import time
import http.server
import socketserver
import urllib.parse
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
# 冻结运行时资源在 PyInstaller 解压目录
_RES = getattr(sys, '_MEIPASS', HERE)
ASSETS = os.path.join(_RES, 'assets')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

import requests
_sess = requests.Session()
_sess.headers.update({'User-Agent': UA, 'Referer': 'https://www.amap.com/'})
_cache = {}
_neg = {}              # key -> 失败时间戳（负缓存）
NEG_TTL = 60.0
CACHE_MAX = 4000

# 客户端断连类异常：静默
_BROKEN = (BrokenPipeError, ConnectionResetError,
           ConnectionAbortedError, socket.timeout)


def _make_placeholder(w=256, h=256):
    """构造全透明 RGBA PNG（zlib 压缩后 ~1KB），启动时生成一次。"""
    raw = b''.join(b'\x00' + b'\x00' * (w * 4) for _ in range(h))

    def chunk(typ, data):
        return (struct.pack('>I', len(data)) + typ + data +
                struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw, 6)) +
            chunk(b'IEND', b''))


PLACEHOLDER = _make_placeholder()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ASSETS, **kw)

    def log_message(self, *a):
        pass

    # 统一入口：吞掉客户端断连，其余异常兜 200 占位瓦片
    def do_GET(self):
        try:
            p = urllib.parse.urlparse(self.path)
            if p.path.startswith('/tile/'):
                return self._tile(p)
            return super().do_GET()
        except _BROKEN:
            return                       # 浏览器已走，静默

    def _fetch(self, remote):
        r = _sess.get(remote, timeout=(4, 6))
        if r.status_code == 200 and r.content:
            return r.content
        return None

    def _tile(self, p):
        # /tile/{z}/{x}/{y}?s=1&style=8
        parts = p.path.strip('/').split('/')
        if len(parts) < 4:
            return self._send(404, b'')
        _, z, x, y = parts[:4]
        q = urllib.parse.parse_qs(p.query)
        sub = q.get('s', ['1'])[0]
        style = q.get('style', ['8'])[0]

        key = (z, x, y, sub, style)
        data = _cache.get(key)
        if data is None:
            # 负缓存：刚失败过的瓦片短期直接给占位
            if time.time() - _neg.get(key, 0) < NEG_TTL:
                return self._send(200, PLACEHOLDER)

            prefix = 'webst0%s' if style == '6' else 'webrd0%s'
            if style == '6':
                fmt = ('https://%s.is.autonavi.com/appmaptile'
                       '?style=6&x=%s&y=%s&z=%s')
                nargs = 4
            else:
                fmt = ('https://%s.is.autonavi.com/appmaptile'
                       '?x=%s&y=%s&z=%s&lang=zh_cn&size=1&scale=1&style=%s')
                nargs = 5
            # 首选子域 -> 再轮换其它子域（挂起主机换个子域经常就能通）
            try:
                sub_i = int(sub)
            except ValueError:
                sub_i = 1
            order = [(sub_i - 1) % 4 + 1,
                     (sub_i % 4) + 1, ((sub_i + 1) % 4) + 1]
            for s in order:
                host = prefix.replace('%s', str(s))
                args = (host, x, y, z)
                if nargs == 5:
                    args = args + (style,)
                try:
                    data = self._fetch(fmt % args)
                except _BROKEN:
                    return
                except Exception:
                    data = None
                if data:
                    break
            if not data:
                _neg[key] = time.time()
                return self._send(200, PLACEHOLDER)

            if len(_cache) < CACHE_MAX:
                _cache[key] = data
            else:
                _cache.clear()
                _cache[key] = data

        self._send(200, data, image=True)

    def _send(self, code, body, image=False):
        try:
            self.send_response(code)
            if image:
                self.send_header('Content-Type', 'image/png')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if body:
                self.wfile.write(body)
        except _BROKEN:
            pass                         # 断连静默


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, _BROKEN):
            return                       # 浏览器断连是常态，不打 traceback
        super().handle_error(request, client_address)


def start(port=0):
    """启动服务器，返回 (server, port)。port=0 表示自动选空闲端口。"""
    srv = Server(('127.0.0.1', port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


if __name__ == '__main__':
    srv, port = start(8765)
    print('serving on http://127.0.0.1:%d/map2.html' % port)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
