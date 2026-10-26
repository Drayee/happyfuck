#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则自适应 —— 把"能跑通"变成"不容易被判无效"

服务端下发 ServerRuleCondition（runningModule/rule/ServerRuleCondition.java）
和 UniRunRuleRespBean，里面有完整的校验维度。上传前必须逐项对表。

关键单位（已从代码确认）
------------------------
averagePace = keepTime(秒) / gpsTotalDistance(km)      // f.l.c.e.a.a()
  → 单位是「秒/公里」
  → 规则里的 averageSpeedStart/End 就是配速上下界，不是 m/s
    证据：uni-app 里 {title:"平均配速", fn:a, params:["averageSpeedStart","averageSpeedEnd"]}
gpsTotalDistance 用 km，setScale(4)                     // LocationService.O()

校验维度
--------
averageSpeedStart/End      配速区间（秒/公里）
averageCadenceStart/End    步频区间（步/分钟）
effectiveMileageStart/End  单次有效里程窗口（km）
dailyMileage/weeklyMileage/semesterMileage   配额（km）
fixedPointPattern          打卡点模式
fixedPointNumber/Order     打卡点数量/顺序
signPoint                  打卡点坐标（GCJ-02）
rangeRunningRegion         围栏多边形（GCJ-02）
recordEffectiveMileage     是否记录有效里程
"""
import math

import coord as C
import run_sim


class RuleSet:
    """服务端下发的规则，字段名对齐 UniRunRuleRespBean / ServerRuleCondition。

    实测（四川农业大学 2026-10）单位：
      averageSpeedStart/End = 毫秒/公里（180000 = 180 s/km = 3分/公里）
      effectiveMileage* / daily/weekly/semesterMileage = 公里
      runningTimeLimit.openTimes.dayStartTime = 当日毫秒偏移
    """

    def __init__(self, d=None):
        d = d or {}
        self.raw = d
        # 兼容两种结构：扁平字段，或 {rule, range:{rangeRunningRegion, signPoint}}
        rule = d.get('rule', d)
        rng = d.get('range', {})
        if not isinstance(rng, dict):
            rng = {}
        src = dict(rule)
        # 围栏/打卡点放在 range 下时，合并到查找表
        src['rangeRunningRegion'] = rng.get('rangeRunningRegion',
                                           rule.get('rangeRunningRegion'))
        src['signPoint'] = rng.get('signPoint', rule.get('signPoint'))
        src['semesterId'] = d.get('semesterId') or rule.get('semesterId')
        src['hasRule'] = rule.get('hasRule', d.get('hasRule'))
        src['runningTimeLimit'] = rule.get('runningTimeLimit',
                                          d.get('runningTimeLimit'))
        d = src
        self.pace_min = self._norm_pace(_f(d.get('averageSpeedStart')))
        self.pace_max = self._norm_pace(_f(d.get('averageSpeedEnd')))
        self.cad_min = _f(d.get('averageCadenceStart'))
        self.cad_max = _f(d.get('averageCadenceEnd'))
        self.mileage_min = _f(d.get('effectiveMileageStart'))
        self.mileage_max = _f(d.get('effectiveMileageEnd'))
        self.daily = _f(d.get('dailyMileage'))
        self.weekly = _f(d.get('weeklyMileage'))
        self.semester = _f(d.get('semesterMileage'))
        self.fixed_number = d.get('fixedPointNumber')
        self.fixed_order = d.get('fixedPointOrder')
        self.fixed_pattern = d.get('fixedPointPattern')
        self.scope_pattern = d.get('scopePattern')
        self.scope_pct = _f(d.get('scopePercentage'))
        self.has_rule = bool(d.get('hasRule'))
        self.sign_points = _pts(d.get('signPoint'))
        self.fence = _fence(d.get('rangeRunningRegion'))
        self.lgs_id = d.get('limitationsGoalsSexInfoId')
        self.semester_id = d.get('semesterId')
        self.scoring_type = d.get('scoringType')
        self.record_msg = d.get('recordEffectiveMileageMsg')
        self.record_effective = d.get('recordEffectiveMileage')
        # 开放时段（范围跑：几点到几点能跑）
        self.open_start, self.open_end = self._parse_open_times(
            d.get('runningTimeLimit'))

    @staticmethod
    def _norm_pace(v):
        """毫秒/公里 -> 秒/公里。>10000 判定为毫秒单位。"""
        if v is None:
            return None
        return v / 1000.0 if v > 10000 else v

    @staticmethod
    def _parse_open_times(rtl):
        if not isinstance(rtl, dict):
            return None, None
        ots = rtl.get('openTimes') or rtl.get('weekOpenTimes') or []
        if not ots:
            return None, None
        ot = ots[0]
        st = ot.get('dayStartTime')
        en = ot.get('dayEndTime')
        try:
            return int(st) // 60000, int(en) // 60000   # 当日分钟数
        except Exception:
            return None, None

    def in_open_window(self, dt=None):
        """当前是否在开放时段内（None=无限制）。"""
        if self.open_start is None:
            return True
        from datetime import datetime
        dt = dt or datetime.now()
        mins = dt.hour * 60 + dt.minute
        return self.open_start <= mins <= self.open_end

    # ------------------------------------------------------------------
    def check(self, vo):
        """对一份 UploadRunInfoReqVo 做规则体检，返回 (ok, problems, warns)。"""
        problems, warns = [], []

        # 1. 配速（VO.avePace 与规则下发都是 毫秒/公里；兼容 s/km 旧格式）
        pace = vo.get('avePace') or 0
        if pace > 10000:            # ms/km（如 450000 = 450 s/km）
            pace_skm = pace / 1000.0
        else:                        # s/km 旧格式
            pace_skm = pace
        if self.pace_min and self.pace_max:
            lo, hi = sorted([self.pace_min, self.pace_max])
            if not (lo <= pace_skm <= hi):
                problems.append(
                    '配速 %.1f 超出规则区间 [%.0f, %.0f] s/km' % (pace_skm, lo, hi))
            elif not (lo + 8 <= pace_skm <= hi - 8):
                warns.append('配速 %.1f 贴着区间边界，建议往中间靠' % pace_skm)
        elif self.pace_min or self.pace_max:
            warns.append('规则只给了一侧配速边界，无法完整校验')

        # 2. 里程（VO.totalMileage 现在是 **公里**；兼容旧版「米」格式）
        raw_m = vo.get('totalMileage') or 0
        km = raw_m if raw_m < 100 else raw_m / 1000.0
        if self.mileage_min and km < self.mileage_min:
            problems.append('里程 %.3f km 低于单次下限 %.3f' % (km, self.mileage_min))
        if self.mileage_max and km > self.mileage_max:
            problems.append('里程 %.3f km 超出单次上限 %.3f' % (km, self.mileage_max))

        # 3. 步频（VO 里没有步频字段，仅在规则给出有效窗口时提示）
        if self.cad_min and self.cad_max and self.cad_max < 3000:
            warns.append(
                '规则要求步频 [%s, %s] 步/分，但 UploadRunInfoReqVo 无步频字段——'
                '服务端可能从 routineLine 的采样密度反推' % (self.cad_min, self.cad_max))

        # 4. 打卡点
        n_sign = len(vo.get('signPoint') or [])
        if self.fixed_pattern and int(self.fixed_pattern) > 0:
            need = self.fixed_number or 0
            if need and n_sign < need:
                problems.append('打卡点 %d 个，规则要求 %d 个' % (n_sign, need))
            elif need and n_sign > need:
                warns.append('打卡点 %d 个，多于规则要求的 %d 个' % (n_sign, need))

        # 5. 围栏（scopePercentage 语义：至少 N% 的点在范围内）
        if self.fence:
            rl = vo.get('routineLine') or []
            if rl:
                inside = sum(1 for p in rl
                             if point_in_fences(p['latitude'],
                                                p['longitude'], self.fence))
                ratio = inside / len(rl)
                need = (self.scope_pct or 0) / 100.0
                msg = ('围栏内点 %d/%d (%.0f%%)，要求 ≥%.0f%%'
                       % (inside, len(rl), ratio * 100,
                         (self.scope_pct or 0)))
                if ratio < need:
                    problems.append('轨迹在范围内比例不足: ' + msg)
                elif ratio < need + 0.15:
                    warns.append('围栏内比例偏低: ' + msg)

        # 6. 采样窗口
        rl = vo.get('routineLine') or []
        bad = 0
        for i in range(1, len(rl)):
            d = run_sim.haversine(rl[i - 1]['latitude'], rl[i - 1]['longitude'],
                                  rl[i]['latitude'], rl[i]['longitude'])
            if d < run_sim.MIN_STEP or d > run_sim.MAX_STEP:
                bad += 1
        if bad:
            problems.append('%d 个相邻点距离越出 [%.2f, %.1f] 窗口'
                            % (bad, run_sim.MIN_STEP, run_sim.MAX_STEP))

        # 7. 空轨迹
        if not rl:
            problems.append('routineLine 为空——这是最容易被判无效的特征')

        return (not problems), problems, warns

    # ------------------------------------------------------------------
    def suggest(self, target_km=None):
        """按规则反算一组安全参数：配速取中值、里程取窗口内。"""
        out = {}

        if self.pace_min and self.pace_max:
            lo, hi = sorted([self.pace_min, self.pace_max])
            # 取中间 60% 区间，避开边界
            span = hi - lo
            out['pace'] = (lo + span * 0.35 + lo + span * 0.65) / 2
        elif self.pace_min:
            out['pace'] = self.pace_min * 1.25
        elif self.pace_max:
            out['pace'] = self.pace_max * 0.75
        else:
            out['pace'] = 360.0

        if target_km:
            out['distance_km'] = target_km
        elif self.mileage_min and self.mileage_max:
            lo, hi = sorted([self.mileage_min, self.mileage_max])
            out['distance_km'] = (lo + hi) / 2
        elif self.mileage_min:
            out['distance_km'] = self.mileage_min * 1.3
        elif self.mileage_max:
            out['distance_km'] = self.mileage_max * 0.8
        else:
            out['distance_km'] = 2.0

        # 时长 = 配速 * 里程
        out['duration'] = int(round(out['pace'] * out['distance_km']))

        # 日配额提醒
        if self.daily:
            out['daily_note'] = '日上限 %.2f km' % self.daily
        return out


# ---------------------------------------------------------------------------
def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _pts(v):
    if not v:
        return []
    return [(p['latitude'], p['longitude']) for p in v
            if isinstance(p, dict) and 'latitude' in p]


def _fence(v):
    if not v:
        return []
    out = []
    if isinstance(v[0], list):
        for poly in v:
            out.append(_pts(poly))
    else:
        out.append(_pts(v))
    return [p for p in out if len(p) >= 3]


def point_in_fences(lat, lon, fences):
    """点是否落在任一围栏多边形内（射线法）。"""
    for poly in fences:
        if point_in_poly(lat, lon, poly):
            return True
    return False


def point_in_poly(lat, lon, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if ((xi > lon) != (xj > lon)) and \
           (lat < (yj - yi) * (lon - xi) / (xj - xi + 1e-12) + yi):
            inside = not inside
        j = i
    return inside


def distance_to_fence(lat, lon, fences):
    """点到最近围栏边界的距离（米），在内部返回 0。"""
    if point_in_fences(lat, lon, fences):
        return 0.0
    best = 1e18
    for poly in fences:
        n = len(poly)
        for i in range(n):
            a = poly[i]
            b = poly[(i + 1) % n]
            best = min(best, _point_seg_dist(lat, lon, a, b))
    return best


def _point_seg_dist(lat, lon, a, b):
    """点到线段的近似距离（米），小范围内用平面近似。"""
    ay, ax = a
    by, bx = b
    py, px = lat, lon
    # 转到米制局部坐标
    m = 111320.0
    coslat = math.cos(math.radians(lat))
    ax_, ay_ = ax * m * coslat, ay * m
    bx_, by_ = bx * m * coslat, by * m
    px_, py_ = px * m * coslat, py * m
    dx, dy = bx_ - ax_, by_ - ay_
    L2 = dx * dx + dy * dy
    if L2 <= 0:
        return math.hypot(px_ - ax_, py_ - ay_)
    t = max(0.0, min(1.0, ((px_ - ax_) * dx + (py_ - ay_) * dy) / L2))
    cx, cy = ax_ + t * dx, ay_ + t * dy
    return math.hypot(px_ - cx, py_ - cy)


# ---------------------------------------------------------------------------
