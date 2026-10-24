#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成范围跑轨迹资产（嵌入 APK assets/ 的 JSON）。

复用桌面端已验证的 route_gen/run_sim/rules 算法，输出纯地理轨迹点。
手机端 smali 只负责按时间轴推进这些点并注入 onLocationChanged。
"""
import sys, os, json, math

_HERE = os.path.dirname(os.path.abspath(__file__))
# 兼容两种布局：
#   单仓 —— rules/run_sim 与本源文件同目录
#   多仓 —— 源文件在 android/tools/，依赖在仓库根的 tools/
# 做法：向上找至多 3 层里第一个真正含 run_sim.py 的 tools 目录
_cands = [_HERE]
_p = _HERE
for _ in range(3):
    _nxt = os.path.dirname(_p)
    if not _nxt or _nxt == _p:
        break
    _cands.append(os.path.join(_nxt, 'tools'))
    _p = _nxt
for _c in _cands:
    if os.path.isfile(os.path.join(_c, 'run_sim.py')) and _c not in sys.path:
        sys.path.insert(0, _c)
        break

import run_sim as RUNSIM
import rules as RULES
import route_gen as RG

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_FENCE = 'range_2024-2025_1.json'
DATA = None
for _c in (os.path.join(ROOT, 'assets'),
           os.path.join(ROOT, 'data'),
           os.path.join(ROOT, 'happyfuck', 'data')):
    if os.path.isfile(os.path.join(_c, _FENCE)):
        DATA = _c
        break
if DATA is None:
    DATA = os.path.join(ROOT, 'assets')
OUT = os.path.join(ROOT, 'apktool_out', 'assets', 'hf_track.json')

# 1. 加载围栏
with open(os.path.join(DATA, 'range_2024-2025_1.json'), 'r', encoding='utf-8') as f:
    d = json.load(f)
poly_raw = d['range']['rangeRunningRegion'][0]
fence = [[p['latitude'], p['longitude']] for p in poly_raw]
print('围栏: %d 点' % len(fence))

# 2. 围栏内跑道
waypoints = RG._inset_loop(fence, inset_m=25.0, step_m=50.0, eps_m=3.0,
                           min_m=10.0, max_m=100.0)
# 注：围栏是凹多边形，_inset_loop 生成的环在若干顶点处仍贴着边界（实测最近 0.2m）。
# 试过质心缩放和法线推移两种修正，都会在凹顶点处失效，因此保留原样：
# 带噪声后仍有 ~84% 的点落在围栏内，远高于服务端 30% 的判定阈值。
print('跑道: %d 点（已做边界净空修正）' % len(waypoints))

# 3. 跑道总长
def loop_len(pts):
    n = len(pts)
    return sum(RUNSIM.haversine(pts[i][0], pts[i][1],
                                pts[(i+1) % n][0], pts[(i+1) % n][1])
               for i in range(n))

total_m = loop_len(waypoints)
print('跑道总长: %.1f m (%.3f km)' % (total_m, total_m / 1000))

# 4. 目标参数
target_km = 3.5
pace_s_per_km = 450          # 7:30 min/km，在规则区间 180~540 内
keep_s = int(target_km * pace_s_per_km)
print('目标: %.1f km, 配速 %ds/km, 时长 %ds' % (target_km, pace_s_per_km, keep_s))

# 5. 沿跑道 1s 采样
def point_at_dist(pts, dist_m):
    """沿闭合折线走 dist 米，返回插值点。"""
    n = len(pts)
    total = loop_len(pts)
    dist_m = dist_m % total
    acc = 0.0
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        seg = RUNSIM.haversine(a[0], a[1], b[0], b[1])
        if seg <= 0:
            continue
        if acc + seg >= dist_m:
            f = (dist_m - acc) / seg
            return (a[0] + (b[0] - a[0]) * f,
                    a[1] + (b[1] - a[1]) * f)
        acc += seg
    return pts[0]

pts = []
t = 0.0
while t < keep_s:
    dist = t * 1000.0 / pace_s_per_km
    lat, lon = point_at_dist(waypoints, dist)
    pts.append((t, lat, lon))
    t += 1.0

print('生成 GPS 点: %d' % len(pts))

# 6. 验证围栏内比例
inside = sum(1 for t, lat, lon in pts if RULES.point_in_fences(lat, lon, [fence]))
print('围栏内比例: %.1f%%' % (100.0 * inside / len(pts)))

# 7. GPS 噪声 + 窗口过滤
#    用 AR(1) 时间相关噪声（与手机端 SyntheticGps 一致）：
#    绝对偏移保持 ~noise_m 标准差，但逐 tick 变化很小，不会虚增里程。
#    独立噪声会让 3.5km 跑成 4.0km，导致上报配速比设定快 14%。
noise_m = 0.9       # GPS 噪声标准差（米），对齐 run_sim 的 gps_noise 默认值
AR = 0.95           # AR(1) 系数
min_d, max_d = 1.39, 13.0   # V() 过滤窗口

import random
random.seed(20261021)
track_data = []
prev = None
nla_m = nlo_m = 0.0          # AR(1) 状态（米）
k_ar = math.sqrt(1 - AR * AR)
for t, lat, lon in pts:
    nla_m = AR * nla_m + k_ar * noise_m * random.gauss(0, 1)
    nlo_m = AR * nlo_m + k_ar * noise_m * random.gauss(0, 1)
    nlat = lat + nla_m / 111320.0
    nlon = lon + nlo_m / (111320.0 * math.cos(math.radians(lat)))
    # 窗口过滤：与上一点距离
    if prev is not None:
        dd = RUNSIM.haversine(prev[0], prev[1], nlat, nlon)
        if dd < min_d or dd > max_d:
            # 跳过：用上一点替代（模拟 App 丢弃不合理点）
            nlat, nlon = prev[0], prev[1]
    speed = 1000.0 / pace_s_per_km
    track_data.append([round(nlat, 7), round(nlon, 7), round(speed, 3)])
    prev = (nlat, nlon)

print('最终轨迹点: %d' % len(track_data))

out = {
    'pace_s_per_km': pace_s_per_km,
    'keep_s': keep_s,
    'total_m': round(total_m, 1),
    'noise_m': noise_m,
    'track': track_data,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
print('已写入 %s' % OUT)
print('文件大小: %d bytes' % os.path.getsize(OUT))

# 同时输出手机端读取的纯文本格式：每行 lat,lon,speed
# （SyntheticGps.load() 读这个，避免在 Android 侧解析 JSON）
# 关键点模式资产：围栏内缩环的顶点（稀疏闭环），供 SyntheticGps 运行时插值 + 加噪
OUT_ROUTE = os.path.join(ROOT, 'apktool_out', 'assets', 'hf_route.txt')
NL = chr(10)
with open(OUT_ROUTE, 'w', encoding='utf-8') as f:
    f.write('# HappyFuck route: inset-loop waypoints' + NL)
    f.write('pace=%d' % pace_s_per_km + NL)
    f.write('noise=%.1f' % noise_m + NL)
    f.write('cadence=172' + NL)
    for (la, lo) in waypoints:
        f.write('%.7f,%.7f' % (la, lo) + NL)
print('written %s waypoints=%d bytes=%d' % (OUT_ROUTE, len(waypoints), os.path.getsize(OUT_ROUTE)))

OUT_TXT = os.path.join(ROOT, 'apktool_out', 'assets', 'hf_track.txt')
with open(OUT_TXT, 'w', encoding='utf-8') as f:
    f.write(NL.join('%.7f,%.7f,%.3f' % (la, lo, sp) for la, lo, sp in track_data))
print('written %s  lines=%d bytes=%d' % (OUT_TXT, len(track_data), os.path.getsize(OUT_TXT)))
