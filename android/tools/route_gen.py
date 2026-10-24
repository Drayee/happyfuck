#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""围栏内轨道生成共享模块。

主代码 (main_window.py) 从这里导入，避免依赖 Qt；
可直接在主机上做纯地理验证（headless）。
"""
import math

import rules as R
import run_sim as RUNSIM


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


def _loop_len(pts):
    n = len(pts)
    if n < 2:
        return 0.0
    return sum(RUNSIM.haversine(pts[i][0], pts[i][1], pts[(i + 1) % n][0],
                                pts[(i + 1) % n][1]) for i in range(n))


def _inset_loop(poly, inset_m=25.0, step_m=50.0, eps_m=3.0,
                min_m=10.0, max_m=100.0):
    """在多边形内部生成一条贴近边界的环形跑道（所有顶点在范围内）。

    旧版只偏移 9 个稀疏顶点：稀疏顶点之间的**直线段**会横穿凹形
    围栏的颈部/凹口，导致 80% 采样点落在围栏外（范围跑要求 ≥30% 在内）。
    新版四步：
      1) 沿原始边界稠密采样（每 12 米一点，记录所属边）；
      2) 每个采样点沿所属边内法线内缩（深度试探，两侧都试，保证落进内部）；
      3) 闭合 Douglas-Peucker 简化；
      4) **等距重采样**：保证相邻点距 ∈ [min_m, max_m]（默认 10~100m），
         且严格沿路线顺序连续，不跳点不交叉。
    """
    m = 111320.0
    fences = [poly]
    n = len(poly)
    # 边界稠密采样用固定细步长（12m），与最终输出步长解耦
    dense_step = 12.0

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
        k = max(1, int(round(seg / dense_step)))
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
        simp = _dp_closed(ring, far, eps_m, m)
    else:
        simp = ring

    # 4) 兜底：简化后的弦可能局部外凸，逐点检查并收拢
    out = []
    for p in simp:
        if inside(p):
            out.append(p)
            continue
        q = _nearest_foot(p, poly)
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
                   if found else _nearest_foot(poly[0], poly))

    # 5) 等距重采样：DP 后点距极不均匀（20m~300m），
    #    重采样到 10~100m 均匀间距，保证连续且不跳点
    out = _resample_loop(out, step_m=step_m, min_m=min_m, max_m=max_m)
    return out


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


# ---------------------------------------------------------------------------
# 等距重采样：保证相邻点距落在 [min_m, max_m]，且沿路线顺序连续
# ---------------------------------------------------------------------------
def _resample_loop(loop, step_m=50.0, min_m=10.0, max_m=100.0):
    """把闭合折线按固定弧长 step_m 等距重采样。

    为什么需要：DP 简化后点距极不均匀（有的 20m、有的 300m），
    而范围跑要求轨迹点连续且间距合理。这里沿路线累计弧长均匀取点，
    最后一段若短于 min_m 就与前一点合并（均分），确保：
      · 每段 ∈ [min_m, max_m]
      · 点序严格沿路线顺序（不跳、不交叉）
      · 首尾闭合
    """
    n = len(loop)
    if n < 3:
        return list(loop)

    # 各段长度与总长
    segs = []
    total = 0.0
    for i in range(n):
        a = loop[i]
        b = loop[(i + 1) % n]
        d = RUNSIM.haversine(a[0], a[1], b[0], b[1])
        segs.append(d)
        total += d
    if total <= 0:
        return list(loop)

    # 点太少就按步长加密；点太多就放宽步长
    cnt = int(round(total / step_m))
    if cnt < 3:
        cnt = 3
    # 保证平均间距不超过 max_m、不小于 min_m
    avg = total / cnt
    if avg > max_m:
        cnt = int(total // max_m) + 1
    elif avg < min_m:
        cnt = int(total // min_m)
        if cnt < 3:
            cnt = 3

    def point_at(s):
        """沿闭合折线走 s 米，返回插值点（含跨段）。"""
        s = s % total
        acc = 0.0
        for i in range(n):
            d = segs[i]
            if d <= 0:
                continue
            if acc + d >= s:
                f = (s - acc) / d
                a = loop[i]
                b = loop[(i + 1) % n]
                return (a[0] + (b[0] - a[0]) * f,
                        a[1] + (b[1] - a[1]) * f)
            acc += d
        return loop[0]

    out = [point_at(total * i / cnt) for i in range(cnt)]
    return _fix_spacing(out, min_m, max_m, step_m)


def _fix_spacing(pts, min_m, max_m, step_m):
    """后处理：把所有越界段修复到 [min_m, max_m] 内。

    策略（反复扫描直到全部合规）：
      · 段 < min_m：删除该段的起点（与前一段合并），或与后一段合并均分
      · 段 > max_m：在该段中间插点等分
    因为是闭合环，扫描包含首尾段。
    """
    pts = list(pts)
    for _ in range(40):
        n = len(pts)
        if n < 5:
            break
        dists = [RUNSIM.haversine(pts[i][0], pts[i][1],
                                  pts[(i + 1) % n][0], pts[(i + 1) % n][1])
                 for i in range(n)]
        short = [i for i, d in enumerate(dists) if d < min_m]
        long_ = [i for i, d in enumerate(dists) if d > max_m]
        if not short and not long_:
            break

        if long_:
            # 优先拆分超长段（插点），这是无损的
            i = long_[0]
            a = pts[i]
            b = pts[(i + 1) % n]
            d = dists[i]
            k = int(d // max_m) + 1
            if k < 2:
                k = 2
            newpts = []
            for j in range(1, k):
                f = j / float(k)
                newpts.append((a[0] + (b[0] - a[0]) * f,
                               a[1] + (b[1] - a[1]) * f))
            pts = pts[:i + 1] + newpts + pts[i + 1:]
            continue

        # 只剩碎步：删除过短段的起点（合并到前一段）
        i = short[0]
        # 删除 pts[(i+1) % n] 这个点，让 i 段与前一段合成一段
        j = (i + 1) % n
        pts.pop(j)
        if j == 0 and pts:
            # 删的是首点，把原来的次点变成首点即可（列表已变）
            pass

    return pts



def clamp_points_into_fence(pts, fences, max_pull_m=40.0):
    """把落在围栏外的采样点吸附回围栏内部。

    服务端按 jadx LocationService.Q() 累计：
        isRangeFence ? effectiveDistance += seg : invalidDistance += seg
    再按 serRangeThreshold 判断（invalid <= gps*thr 则全部算有效）。
    若我们上报 effective==gps（invalid 隐含 0），而轨迹有 16% 在围栏外，
    一旦阈值 <16% 数据就自相矛盾 -> 判异常。故此处把越界点拉回内部。

    实现：对每个外点，沿 12 个方向 × 逐级距离探测，找第一个落入内部的点。
    （不能用「拉向最近边界点」——从外到边界的整段路径仍在外部。）
    """
    if not fences or not pts:
        return list(pts)

    m_per_deg_lat = 111320.0
    import math as _m

    def inside(lat, lon):
        return R.point_in_fences(lat, lon, fences)

    out = []
    fixed = 0
    for p in pts:
        t, lat, lon = p
        if inside(lat, lon):
            out.append(p)
            continue

        coslat = _m.cos(_m.radians(lat)) or 1e-9
        got = None
        # 逐级加大距离，12 个方向
        for dist in (6.0, 10.0, 16.0, 24.0, max_pull_m):
            dlat_u = dist / m_per_deg_lat
            dlon_u = dist / (m_per_deg_lat * coslat)
            for k in range(12):
                ang = 2 * _m.pi * k / 12.0
                nlat = lat + dlat_u * _m.cos(ang)
                nlon = lon + dlon_u * _m.sin(ang)
                if inside(nlat, nlon):
                    got = (t, nlat, nlon)
                    break
            if got:
                break
        if got:
            out.append(got)
            fixed += 1
        else:
            out.append(p)          # 拉不动就保留（极端情况）
    return out


def resample_track(pts, step_m=2.5):
    """沿折线等距重采样轨迹，保证点距落在 V() 窗口内。

    背景：围栏吸附会改变点间距（有的被拉近到 1.3m、有的撑开到 25m），
    build_vo 的 V() 窗口过滤会丢弃大量点，导致里程大幅缩水。
    这里按固定步长重新插值，使点距均匀、全部落在 [1.39, 13.0] 内。
    时间戳按弧长比例线性分配，保持配速含义。
    """
    if len(pts) < 2:
        return list(pts)
    t0 = pts[0][0]
    t1 = pts[-1][0]
    total = 0.0
    segs = []
    for i in range(1, len(pts)):
        d = RUNSIM.haversine(pts[i - 1][1], pts[i - 1][2],
                             pts[i][1], pts[i][2])
        segs.append(d)
        total += d
    if total <= 0:
        return list(pts)

    n = max(2, int(round(total / step_m)))
    dt = (t1 - t0) / max(1, n)

    out = []
    acc = 0.0
    si = 0
    for k in range(n + 1):
        target = total * k / n
        while si < len(segs) - 1 and acc + segs[si] < target:
            acc += segs[si]
            si += 1
        d = segs[si] if si < len(segs) else 1.0
        f = (target - acc) / d if d > 0 else 0.0
        f = max(0.0, min(1.0, f))
        a = pts[si]
        b = pts[si + 1] if si + 1 < len(pts) else pts[si]
        lat = a[1] + (b[1] - a[1]) * f
        lon = a[2] + (b[2] - a[2]) * f
        out.append((t0 + dt * k, lat, lon))
    return out


def dist_point_to_segment_m(p, a, b):
    """点到线段距离（米），平面近似。p/a/b = (lat, lon)。"""
    kx = 111320.0 * math.cos(math.radians(p[0]))
    ky = 111320.0
    px, py = p[1] * kx, p[0] * ky
    ax, ay = a[1] * kx, a[0] * ky
    bx, by = b[1] * kx, b[0] * ky
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def clearance_m(p, fence):
    """点到围栏边界的最小距离（米）。"""
    m = len(fence)
    return min(dist_point_to_segment_m(p, fence[i], fence[(i + 1) % m])
               for i in range(m))


def pull_inside(fence, loop, clearance=15.0, iters=12):
    """把离边界太近的环点沿「最近边的内法线」推开，保证净空 >= clearance 米。

    不能用「朝质心拉」：围栏是凹多边形，朝质心走会直接穿出边界
    （实测栏内比例从 96% 掉到 41%）。这里改为沿最近边的法线推开，
    并对两个方向都做落点校验，取真正落在多边形内的那个。
    """
    import rules as _rules

    n = len(fence)
    out = list(loop)
    for _ in range(iters):
        moved = 0
        for idx, (la, lo) in enumerate(out):
            kx = 111320.0 * math.cos(math.radians(la))
            px, py = lo * kx, la * 111320.0
            best = None
            for i in range(n):
                a = fence[i]
                b = fence[(i + 1) % n]
                ax, ay = a[1] * kx, a[0] * 111320.0
                bx, by = b[1] * kx, b[0] * 111320.0
                dx, dy = bx - ax, by - ay
                l2 = dx * dx + dy * dy
                if l2 == 0:
                    t = 0.0
                else:
                    t = ((px - ax) * dx + (py - ay) * dy) / l2
                    t = max(0.0, min(1.0, t))
                cx, cy = ax + t * dx, ay + t * dy
                dd = math.hypot(px - cx, py - cy)
                if best is None or dd < best[0]:
                    best = (dd, dx, dy)
            dd, dx, dy = best
            if dd >= clearance:
                continue
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-9:
                continue
            nx, ny = -dy / seg_len, dx / seg_len
            step = clearance - dd
            for sign in (1.0, -1.0):
                nla = la + (sign * ny * step) / 111320.0
                nlo = lo + (sign * nx * step) / kx
                if _rules.point_in_poly(nla, nlo, fence):
                    out[idx] = (nla, nlo)
                    moved += 1
                    break
        if moved == 0:
            break
    return out
