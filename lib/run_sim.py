#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人类跑步轨迹模拟器 —— 乐健 UploadRunInfoReqVo 生成器

核心思路
--------
不是"随便造点"，而是复刻 LocationService 的真实采样管线：

  1. 圈定跑道（地图上画多边形，或用预设跑道）
  2. 沿跑道生成"理想路径"，按真实跑者速度曲线推进
  3. 每 1 秒采一次样（App 的 LocationService 采样周期）
  4. 对每个采样点施加 GPS 噪声（人类 + 硬件双重噪声）
  5. 用 V() 的过滤窗口（1.39m < d < 13m）筛掉不合理点
  6. 输出 routineLine / signPoint / 各项统计量

为什么这样能过规则检查
----------------------
- routineLine 是逐点轨迹，不是空数组
- 相邻点距离全部落在 [1.39, 13.0] 米内（正是 V() 的接受窗口）
- 配速随坡度/疲劳自然波动，不是常数
- signPoint 按 50m 半径命中真实打卡点
- 每次运行随机种子不同，签名必然不同

用法
----
  python run_sim.py            # 启动 GUI
  python run_sim.py --headless # 只跑一次生成，输出 JSON
"""
import argparse
import datetime
import json
import math
import os
import random
import sys
import time

import coord as C

# ---------------------------------------------------------------------------
# 常量（全部来自静态逆向）
# ---------------------------------------------------------------------------
EARTH_R = 6371000.0
MIN_STEP = 1.39          # LocationService.V() 下界
MAX_STEP = 13.0          # LocationService.V() 上界
SIGN_RADIUS = 50.0       # U()/W() 打卡判定半径
SAMPLE_DT = 1.0          # 采样周期 1s


def haversine(lat1, lon1, lat2, lon2):
    """AMapUtils.calculateLineDistance 的等价实现（米）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


def offset(lat, lon, dist_m, bearing_deg):
    """从 (lat,lon) 沿 bearing 走 dist_m，返回新坐标。"""
    br = math.radians(bearing_deg)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    dr = dist_m / EARTH_R
    p2 = math.asin(math.sin(p1) * math.cos(dr) + math.cos(p1) * math.sin(dr) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(dr) * math.cos(p1),
                         math.cos(dr) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------------------------------------------------------------------------
# 速度曲线：模拟真实跑者
# ---------------------------------------------------------------------------
class HumanPace:
    """生成随时间变化的速度（m/s），带起步、疲劳、坡度、随机抖动。"""

    def __init__(self, target_pace_s_per_km, duration_s, rng):
        self.rng = rng
        self.base = 1000.0 / target_pace_s_per_km if target_pace_s_per_km > 0 else 2.8
        self.duration = duration_s
        self._phase = rng.uniform(0, math.tau)
        self._fatigue_rate = rng.uniform(0.03, 0.10)

    def speed(self, t):
        """t 秒时的瞬时速度 m/s。"""
        rng = self.rng
        # 1. 起步爬升：前 30 秒从 0.4 倍升到 1 倍
        warm = min(1.0, 0.4 + 0.6 * (t / 30.0)) if t < 30 else 1.0
        # 2. 疲劳衰减：线性下降 fatigue_rate
        fatigue = 1.0 - self._fatigue_rate * (t / max(1.0, self.duration))
        # 3. 呼吸周期抖动：约 3 步一呼吸，频率 0.6Hz 左右
        breath = 1.0 + 0.035 * math.sin(math.tau * 0.6 * t + self._phase)
        # 4. 步频抖动：更高频小幅
        stride = 1.0 + 0.02 * math.sin(math.tau * 2.7 * t + self._phase * 1.7)
        # 5. 随机游走（白噪声累积，模拟注意力漂移）
        walk = 1.0 + rng.gauss(0, 0.012)
        v = self.base * warm * fatigue * breath * stride * walk
        return max(0.3, v)


# ---------------------------------------------------------------------------
# 轨迹生成
# ---------------------------------------------------------------------------
class TrackSim:
    def __init__(self, waypoints, target_pace, duration_s, seed=None,
                 gps_noise=0.9, drop_rate=0.06, src_crs='gcj02'):
        """
        waypoints : [(lat,lon), ...] 跑道顶点（闭合环路）
        target_pace : 目标配速 秒/公里
        duration_s : 目标时长（秒）
        gps_noise : GPS 噪声标准差（米），真实手机 0.5~1.5m
        drop_rate : 采样点丢弃率（模拟信号丢失）
        src_crs : 传入 waypoints 的坐标系
                  'gcj02' -> 原样使用（乐健链路要求的坐标系）
                  'wgs84' -> 自动转 GCJ-02
                  'bd09'  -> 自动转 GCJ-02
        """
        self.src_crs = (src_crs or 'gcj02').lower()
        self.wp = self._to_gcj02(waypoints)
        self.pace = target_pace
        self.duration = duration_s
        self.rng = random.Random(seed)
        self.gps_noise = gps_noise
        self.drop_rate = drop_rate

    def _to_gcj02(self, wps):
        out = []
        for lat, lon in wps:
            if self.src_crs == 'wgs84':
                out.append(C.wgs84_to_gcj02(lat, lon))
            elif self.src_crs == 'bd09':
                out.append(C.bd09_to_gcj02(lat, lon))
            else:
                out.append((lat, lon))
        return out

    def _loop_length(self):
        n = len(self.wp)
        return sum(haversine(*self.wp[i], *self.wp[(i + 1) % n]) for i in range(n))

    def _point_on_loop(self, s):
        """沿闭合环路走 s 米，返回 (lat, lon, heading)。"""
        n = len(self.wp)
        acc = 0.0
        for i in range(n):
            a, b = self.wp[i], self.wp[(i + 1) % n]
            seg = haversine(*a, *b)
            if acc + seg >= s:
                frac = (s - acc) / seg if seg > 0 else 0
                lat = a[0] + (b[0] - a[0]) * frac
                lon = a[1] + (b[1] - a[1]) * frac
                return lat, lon, bearing(*a, *b)
            acc += seg
        # 绕完一圈，取余继续
        return self._point_on_loop(s % max(acc, 1.0))

    def generate(self):
        rng = self.rng
        pace_model = HumanPace(self.pace, self.duration, rng)
        loop_len = self._loop_length()
        if loop_len <= 0:
            raise ValueError('跑道长度为零，检查 waypoints')

        raw = []          # 原始采样 (t, lat, lon)
        s = 0.0           # 沿跑道累计距离
        t = 0.0
        # 起点轻微偏移，避免每次同一起点
        s = rng.uniform(0, loop_len)

        while t <= self.duration:
            lat, lon, head = self._point_on_loop(s)
            # GPS 噪声：沿垂直方向偏移为主（横向误差比纵向大）
            perp = head + 90
            lat_n, lon_n = offset(lat, lon, rng.gauss(0, self.gps_noise), perp)
            lat_n, lon_n = offset(lat_n, lon_n, rng.gauss(0, self.gps_noise * 0.5), head)
            raw.append((t, lat_n, lon_n))

            v = pace_model.speed(t)
            s += v * SAMPLE_DT
            t += SAMPLE_DT

        # V() 过滤：相邻点距离必须落在 [1.39, 13.0]
        filtered = [raw[0]]
        dropped = 0
        for pt in raw[1:]:
            d = haversine(filtered[-1][1], filtered[-1][2], pt[1], pt[2])
            if MIN_STEP <= d <= MAX_STEP:
                # 再模拟信号丢失
                if rng.random() < self.drop_rate:
                    dropped += 1
                    continue
                filtered.append(pt)
            else:
                dropped += 1
                # 距离过小时仍推进（真实 GPS 会重复报点，V() 会 reject）
                if d < MIN_STEP:
                    continue
                # 距离过大时跳点（隧道/高楼），直接接上
                filtered.append(pt)

        return filtered, dropped

    def stats(self, pts):
        """计算 UploadRunInfoReqVo 需要的统计量（按输出精度量化后计算）。"""
        q = [(t, round(la, 7), round(lo, 7)) for t, la, lo in pts]
        total = 0.0
        for i in range(1, len(q)):
            total += haversine(q[i - 1][1], q[i - 1][2], q[i][1], q[i][2])
        keep = int(q[-1][0]) if q else 0
        pace = (keep / total * 1000.0) if total > 0 else 0.0
        return {
            'points': len(q),
            'totalMileage': round(total, 2),
            'keepTime': keep,
            'avePace': round(pace, 2),
        }


def calc_kcal(pace_ms_km, weight_kg, distance_m):
    """复刻 f.l.c.e.a.d(averagePace_ms_km, weight, distance_m) 的 METs 卡路里公式。

    paceMinute = pace_ms / 60000; 若非 0:
      kcal = ((24000 / (7 * paceMinute) + 1) * weight * distance_m * paceMinute
              / 3600000).intValue()
    """
    if pace_ms_km <= 0 or weight_kg <= 0 or distance_m <= 0:
        return 0
    pace_minute = pace_ms_km / 60000.0          # min/km（4 位小数即可）
    m7 = 7.0 * pace_minute
    if m7 <= 0:
        return 0
    per_km_factor = 24000.0 / m7 + 1.0
    kcal = per_km_factor * weight_kg * distance_m * pace_minute / 3600000.0
    return int(kcal)


# ---------------------------------------------------------------------------
# 输出 UploadRunInfoReqVo
# ---------------------------------------------------------------------------
def build_vo(sim_result, cfg):
    pts, _ = sim_result

    # 关键：先按输出精度（7 位小数）量化，再重新做窗口校验。
    # 若先校验后舍入，round(...,6) 的误差（约 0.1m）会把边界点挤出 [1.39,13.0]。
    q = [(t, round(la, 7), round(lo, 7)) for t, la, lo in pts]
    pts = [q[0]] if q else []
    for pt in q[1:]:
        d = haversine(pts[-1][1], pts[-1][2], pt[1], pt[2])
        if MIN_STEP <= d <= MAX_STEP:
            pts.append(pt)
        # 否则丢弃，下一个点继续与最后一个已接受点比较

    total = 0.0
    for i in range(1, len(pts)):
        total += haversine(pts[i - 1][1], pts[i - 1][2], pts[i][1], pts[i][2])
    keep = int(pts[-1][0]) if pts else 0
    pace = (keep / total * 1000.0) if total > 0 else 0.0

    # ---- 单位对齐真实 App（RunningViewModel.n() 反编译确认，2026-10-20）----
    # effectiveMileage / gpsMileage / totalMileage  = **公里**（LocationService.O():
    #       AMapUtils.calculateLineDistance(m)/1000 后 setScale(4)，BigDecimal km）
    # effectivePart  = scoringType==1 时恒为 1（不是米）
    # totalPart      = 0.0（仅 scoringType==2 时是段距 km，来自 serverRule.segmentMileage）
    # paceNumber     = 步数 stepCount（不是分钟数）
    # avePace        = runtimeMillis(ms) / gpsTotalDistance(km) -> **毫秒/公里**
    #       （LocationService: averagePace = f.l.c.e.a.a(gpsTotalDistance_km, c_ms)）
    # type           = RunTypeEnum.title：'范围跑' / '自由跑' / '定点跑'
    km = round(total / 1000.0, 4)
    pace_ms_km = (keep * 1000.0 / km) if km > 0 else 0.0   # ms/km，与服务端一致
    sc = cfg['scoring_type']
    sc_int = int(sc) if str(sc).isdigit() else 1
    eff_part = 1 if sc_int == 1 else int(km)
    # 步数：按步频 165~180 步/分模拟（服务端可能从 routineLine 密度反推）
    cadence = float(cfg.get('cadence') or 172.0)
    steps = int(round(keep / 60.0 * cadence))
    # 卡路里：f.l.c.e.a.d() 的 METs 公式，入参 (pace_ms_km, 体重kg, 距离m)
    weight = float(cfg.get('weight') or 63.0)
    kcal = calc_kcal(pace_ms_km, weight, total)

    routine = [{'latitude': p[1], 'longitude': p[2]} for p in pts]

    # signPoint：找出距离打卡点 50m 内的采样点
    sign_points = []
    for idx, (slat, slon) in enumerate(cfg.get('sign_targets', [])):
        best = None
        for p in pts:
            d = haversine(slat, slon, p[1], p[2])
            if d <= SIGN_RADIUS:
                if best is None or d < best[0]:
                    best = (d, p)
        if best:
            sign_points.append({'signPoint': str(idx), 'state': 1})

    start_ms = cfg['start_ms']
    end_ms = start_ms + keep * 1000
    # 时间字段：服务端要 "yyyy-MM-dd HH:mm:ss" 字符串（实测毫秒字符串会令
    # 整个对象解析失败，报「所有字段 must not be null」）。
    tfmt = datetime.datetime.fromtimestamp(start_ms / 1000.0)\
        .strftime('%Y-%m-%d %H:%M:%S')
    efmt = datetime.datetime.fromtimestamp(end_ms / 1000.0)\
        .strftime('%Y-%m-%d %H:%M:%S')
    # 字段类型严格对齐 UploadRunInfoReqVo 的 smali：
    #   effectiveMileage/gpsMileage/totalMileage/totalPart/avePace = D(double)
    #   effectivePart/paceNumber/keepTime/scoringType/paceRange/calorie = I(int)
    #   startTime/endTime/signTime/type/oct/... = String
    #   endTimeDate = J(long)
    sc = cfg['scoring_type']
    run_type_title = cfg.get('type', '范围跑')   # RunTypeEnum.title
    vo = {
        'avePace': round(pace_ms_km, 2),        # double, **毫秒/公里**
        'calorie': int(cfg['calorie']) if cfg.get('calorie') is not None
                   else kcal,                     # int, kcal（METs 公式）
        'effectiveMileage': km,                 # double, **公里**
        'effectivePart': eff_part,              # int, scoringType==1 → 1
        'endTime': efmt,                        # String, 秒格式
        'startTime': tfmt,                      # String, 秒格式
        'gpsMileage': km,                       # double, **公里**
        'limitationsGoalsSexInfoId': cfg['lgs_id'],
        'paceNumber': steps,                    # int, **步数**
        'paceRange': int(cfg.get('pace_range', 0)),
        'routineLine': routine,
        'scoringType': sc_int,
        'semesterId': cfg['semester_id'],
        'signPoint': sign_points,
        'totalMileage': km,                     # double, **公里**
        'totalPart': 0.0,                       # double, 非段距跑恒 0
        'type': run_type_title,                 # String, '范围跑' 等
        'uneffectiveReason': '',
        'systemVersion': cfg.get('systemVersion', '13'),
        'appVersion': cfg.get('appVersion', '3.10.3'),
        'deviceType': cfg.get('deviceType', 'Pixel 6'),
        'signTime': tfmt,
        'oct': '',
        'signDigital': cfg.get('sign_digital', ''),
        'endTimeDate': end_ms,                  # long, ms
        'keepTime': keep,                       # int, s
    }
    return vo


# ---------------------------------------------------------------------------
# 预设跑道
# ---------------------------------------------------------------------------
PRESETS = {
    '标准400m操场': [
        (39.9042, 116.4074), (39.9042, 116.4102),
        (39.9027, 116.4102), (39.9027, 116.4074),
    ],
    '矩形环路1km': [
        (39.9040, 116.4070), (39.9040, 116.4115),
        (39.9010, 116.4115), (39.9010, 116.4070),
    ],
    '三角环路': [
        (39.9050, 116.4070), (39.9050, 116.4110), (39.9020, 116.4090),
    ],
}
