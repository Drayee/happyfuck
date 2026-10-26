#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 核心服务层。

把 tools/ 下的库封装成界面可直接调用的服务，全部跑在后台线程。
"""
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta

import config as CFG

sys.path.insert(0, CFG.TOOLS)

import coord as C
import rules as R
import run_sim
import legym_envelope as LE
import b_login_upload as BU
from history import History
import uploader


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
class Logger:
    def __init__(self, path, max_lines=2000):
        self.path = path
        self.lines = []
        self.max_lines = max_lines
        self._lock = threading.Lock()

    def log(self, level, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        line = '[%s] %-5s %s' % (ts, level, msg)
        with self._lock:
            self.lines.append(line)
            if len(self.lines) > self.max_lines:
                self.lines = self.lines[-self.max_lines:]
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass

    def info(self, m):
        self.log('INFO', m)

    def warn(self, m):
        self.log('WARN', m)

    def error(self, m):
        self.log('ERROR', m)

    def ok(self, m):
        self.log('OK', m)

    def recent(self, n=200):
        with self._lock:
            return list(self.lines[-n:])


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------
class Session:
    """登录态。"""

    def __init__(self, data=None):
        self.raw = data or {}
        self.access_token = ''
        self.refresh_token = ''
        self.user_id = ''
        self.school_id = ''
        self.semester_id = ''
        self.lgs_id = ''
        self.real_name = ''
        self.nick_name = ''
        self.mobile = ''
        self.school_name = ''
        self.pace_range = 0.0
        if data:
            self.apply(data)

    def apply(self, data):
        self.raw = data
        d = data.get('data') or data
        self.access_token = d.get('accessToken') or d.get('token') or ''
        self.refresh_token = d.get('refreshToken') or ''
        self.user_id = d.get('userId') or d.get('id') or ''
        self.school_id = d.get('schoolId') or d.get('organizationId') or ''
        self.semester_id = d.get('semesterId') or ''
        self.lgs_id = d.get('limitationsGoalsSexInfoId') or ''
        self.real_name = d.get('realName') or ''
        self.nick_name = d.get('nickName') or ''
        self.mobile = d.get('mobile') or ''
        self.school_name = d.get('schoolName') or d.get('organizationName') or ''
        try:
            self.pace_range = float(d.get('paceRange') or 0)
        except Exception:
            self.pace_range = 0.0

    @property
    def valid(self):
        return bool(self.access_token)

    def to_dict(self):
        return self.raw


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------
class Service:
    """所有耗时操作都在后台线程跑，通过回调通知界面。"""

    def __init__(self, cfg=None):
        self.cfg = cfg or CFG.Config()
        self.log = Logger(CFG.LOG_FILE)
        self.session = Session(CFG.load_json(CFG.SESSION_FILE))
        self.ruleset = None
        self.hs = None
        self.history = History()
        self._stop = threading.Event()
        self._running = False

    # ------------------------------------------------------------------
    # 签名
    # ------------------------------------------------------------------
    def check_hs_ready(self):
        """检查签名是否可用，返回 (ok, message)。

        frida 的 add_remote_device/enumerate_applications 对半开 TCP
        可能长时间阻塞，用看门狗线程限时 12s，绝不拖死调用方（GUI 主线程）。
        """
        mode = self.cfg.get('hs_mode')
        if mode != 'frida':
            return self._check_hs_table()
        host = self.cfg.get('frida_host') or '127.0.0.1:27042'
        box = {}

        def probe():
            try:
                import frida
            except ImportError:
                box['r'] = (False, ('未安装 frida 库。\n\n'
                                    '请运行:\n'
                                    '  python -m pip install frida-tools\n\n'
                                    '或者改用「查表签名」方式。'))
                return
            try:
                dev = frida.get_device_manager().add_remote_device(host)
                apps = dev.enumerate_applications()
                target = [a for a in apps
                          if a.identifier == 'com.ledreamer.zz']
                if not target:
                    box['r'] = (False, ('已连上 %s，但没找到乐健 App。\n\n'
                                        '请先在手机上打开乐健体育。' % host))
                else:
                    box['r'] = (True, 'Frida 已连接，乐健 App 在运行')
            except Exception as e:
                box['r'] = (False, ('连不上 frida-server (%s)\n\n'
                                    '请确认:\n'
                                    '1. 手机已用 USB 连接\n'
                                    '2. 已运行 frida-server\n'
                                    '3. 已执行 adb forward tcp:27042 tcp:27042\n\n'
                                    '错误: %s' % (host, e)))

        t = threading.Thread(target=probe, daemon=True)
        t.start()
        t.join(12.0)
        if box:
            return box['r']
        return False, ('检查超时（12 秒）。\n\n'
                       '%s 可能连上了一个挂死的端口（比如 adb forward 指向'
                       '没有 frida-server 的设备）。请确认模拟器/真机上'
                       'frida-server 已启动。' % host)

    def _check_hs_table(self):
        p = self.cfg.get('hs_table')
        if not os.path.isabs(p):
            p = os.path.join(CFG.DATA_DIR, p)
        if not os.path.exists(p):
            return False, ('签名表不存在:\n%s\n\n'
                           '请先用 Frida 抓一次签名表，\n'
                           '或用「Frida 实时签名」方式。' % p)
        try:
            import json as _j
            with open(p, 'r', encoding='utf-8') as f:
                t = _j.load(f)
            return True, '签名表已加载（%d 条记录）' % len(t)
        except Exception as e:
            return False, '签名表读取失败: %s' % e

    def get_hs(self):
        if self.hs is not None:
            return self.hs
        mode = self.cfg.get('hs_mode')
        if mode == 'frida':
            self.hs = BU.FridaRpcHs(self.cfg.get('frida_host'))
            self.log.info('签名: Frida RPC @ %s' % self.cfg.get('frida_host'))
        else:
            p = self.cfg.get('hs_table')
            if not os.path.isabs(p):
                p = os.path.join(CFG.DATA_DIR, p)
            self.hs = BU.StaticTableHs(p)
            self.log.info('签名: 查表 %s' % p)
        return self.hs

    def reset_hs(self):
        self.hs = None

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------
    def login(self, phone, password, on_done=None, on_log=None):
        """真实账号密码登录。

        已验证（2026-10-20 实测）：
          - 服务端 **不校验** signDigital（空签名登录返回 code=0）
          - 响应 data 是嵌套 envelope {t, pyd}，用 getDyKey 解密
          - 因此登录完全不需要 Frida
        """
        def worker():
            try:
                self.log.info('开始登录 %s' % phone)
                if on_log:
                    on_log('正在登录…')

                # 先尝试带签名（若已配置），否则空签名 —— 服务端都接受
                sign = ''
                hs_ok = False
                ok_hs, msg_hs = self.check_hs_ready()
                if ok_hs:
                    try:
                        hs = self.get_hs()
                        sign = hs.hs(phone + password +
                                     (self.cfg.get('entrance') or '1'))
                        hs_ok = True
                        self.log.info('登录签名已计算')
                    except Exception as e:
                        self.log.warn('签名计算失败，改用空签名: %s' % e)
                else:
                    self.log.info('签名未配置，使用空签名登录（服务端不校验）')

                body = {
                    'userName': phone,
                    'password': password,
                    'signDigital': sign,
                    'phone': phone,
                    'entrance': self.cfg.get('entrance') or '1',
                }
                ts = int(time.time() * 1000)
                env = LE.wrap_request(
                    json.dumps(body, ensure_ascii=False,
                               separators=(',', ':')), ts)

                import urllib.request
                import urllib.error
                req = urllib.request.Request(
                    BU.BASE + 'authorization/user/v2/manage/login',
                    data=json.dumps(env).encode(),
                    headers={'Content-Type': 'application/json; charset=UTF-8',
                             'User-Agent': 'okhttp/4.9.3'},
                    method='POST')
                try:
                    with urllib.request.urlopen(req, timeout=15) as r:
                        txt = r.read().decode('utf-8', 'replace')
                except urllib.error.HTTPError as e:
                    txt = e.read().decode('utf-8', 'replace')

                obj = json.loads(txt)
                code = obj.get('code')
                msg = obj.get('message')

                if code != 0:
                    self.log.error('登录被拒: code=%s %s' % (code, msg))
                    if on_done:
                        on_done(False, msg or ('登录失败 code=%s' % code))
                    return

                # 嵌套 envelope 解密
                d = obj.get('data')
                if isinstance(d, dict) and 'pyd' in d:
                    d = json.loads(LE.unwrap_response(d))
                obj['data'] = d or {}
                self.session.apply(obj)
                CFG.save_json(CFG.SESSION_FILE, obj)

                if not self.session.valid:
                    self.log.error('登录返回里没有 accessToken')
                    if on_done:
                        on_done(False, '返回异常：没有 accessToken')
                    return

                # 补账号字段
                if self.session.semester_id:
                    self.cfg.set('semester_id', self.session.semester_id)
                if self.session.lgs_id:
                    self.cfg.set('lgs_id', self.session.lgs_id)
                if self.session.school_id:
                    self.cfg.set('school_id', self.session.school_id)
                self.cfg.set('phone', phone)
                self.cfg.set('password', password)
                self.cfg.save()

                self.log.ok('登录成功: %s (%s)%s'
                            % (self.session.real_name or phone,
                               self.session.school_name or
                               self.session.school_id,
                               '' if hs_ok else ' [空签名]'))
                if on_done:
                    on_done(True, '登录成功')
            except Exception as e:
                self.log.error('登录异常: %s' % e)
                self.log.error(traceback.format_exc()[-400:])
                if on_done:
                    on_done(False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # token 续期（已验证 code=0）
    # ------------------------------------------------------------------
    def refresh_token(self, on_done=None):
        def worker():
            try:
                if not self.session.refresh_token:
                    if on_done:
                        on_done(False, '没有 refreshToken')
                    return
                import urllib.request
                import urllib.error
                url = (BU.BASE + 'authorization/user/refreshToken?refreshToken='
                       + self.session.refresh_token)
                req = urllib.request.Request(
                    url,
                    headers={'Content-Type': 'application/json',
                             'User-Agent': 'okhttp/4.9.3',
                             'Authorization': 'Bearer ' + self.session.access_token,
                             'Organization': str(self.session.school_id)},
                    method='GET')
                try:
                    with urllib.request.urlopen(req, timeout=15) as r:
                        txt = r.read().decode('utf-8', 'replace')
                except urllib.error.HTTPError as e:
                    txt = e.read().decode('utf-8', 'replace')
                obj = json.loads(txt)
                d = obj.get('data')
                if isinstance(d, dict) and 'pyd' in d:
                    d = json.loads(LE.unwrap_response(d))
                if obj.get('code') == 0 and d:
                    self.session.access_token = d.get('accessToken') or \
                        self.session.access_token
                    self.session.refresh_token = d.get('refreshToken') or \
                        self.session.refresh_token
                    # 更新过期时间（下次启动据此判断是否续期）
                    raw = self.session.raw.get('data')
                    if isinstance(raw, dict):
                        raw['accessToken'] = self.session.access_token
                        raw['refreshToken'] = self.session.refresh_token
                        if d.get('accessTokenExpires'):
                            raw['accessTokenExpires'] = d['accessTokenExpires']
                    CFG.save_json(CFG.SESSION_FILE, self.session.raw)
                    self.log.ok('token 已续期')
                    if on_done:
                        on_done(True, 'ok')
                else:
                    self.log.error('续期失败: %s' % obj.get('message'))
                    if on_done:
                        on_done(False, str(obj.get('message')))
            except Exception as e:
                self.log.error('续期异常: %s' % e)
                if on_done:
                    on_done(False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # 学期（已验证: GET education/semester/queryAll, 明文, current==1 为在读）
    # ------------------------------------------------------------------
    def fetch_semester(self, on_done=None):
        def worker():
            try:
                import urllib.request
                import urllib.error
                req = urllib.request.Request(
                    BU.BASE + 'education/semester/queryAll',
                    headers={'Content-Type': 'application/json',
                             'User-Agent': 'okhttp/4.9.3',
                             'Authorization': 'Bearer ' + self.session.access_token,
                             'Organization': str(self.session.school_id)},
                    method='GET')
                try:
                    with urllib.request.urlopen(req, timeout=15) as r:
                        txt = r.read().decode('utf-8', 'replace')
                except urllib.error.HTTPError as e:
                    txt = e.read().decode('utf-8', 'replace')
                obj = json.loads(txt)
                sems = obj.get('data') or []
                if isinstance(sems, dict) and 'pyd' in sems:
                    sems = json.loads(LE.unwrap_response(sems))
                cur = [s for s in sems if s.get('current') == 1]
                sem_id = (cur or sems)[-1].get('id') if sems else None
                if sem_id:
                    self.cfg.set('semester_id', sem_id)
                    self.cfg.save()
                    self.log.ok('学期: %s' % sem_id)
                if on_done:
                    on_done(bool(sem_id), sem_id)
            except Exception as e:
                self.log.error('学期获取异常: %s' % e)
                if on_done:
                    on_done(False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # 拉规则
    # ------------------------------------------------------------------
    def fetch_rules(self, lat=None, lon=None, on_done=None, on_log=None):
        def worker():
            try:
                if not self.session.valid:
                    if on_done:
                        on_done(False, '未登录')
                    return
                if on_log:
                    on_log('正在拉取学校规则…')

                # 实测：学期 + getRunningLimit 走明文即可，自由跑 hasRule=false
                sem = self.cfg.get('semester_id') or self.session.semester_id
                if not sem:
                    ok_s, sem = self._fetch_semester_sync()
                    if not ok_s:
                        if on_done:
                            on_done(False, '拿不到学期 ID')
                        return

                d = self._post_plain('running/app/getRunningLimit',
                                     {'semesterId': sem})
                if not d:
                    if on_done:
                        on_done(False, 'getRunningLimit 无数据')
                    return

                # 范围跑：hasRule=true 时再拉围栏 getRunningRange
                if d.get('hasRule'):
                    rng = self._post_plain(
                        'running/app/getRunningRange', {
                            'latitude': lat or (self.cfg.get('map_center') or [30.6948, 103.8508])[0],
                            'longitude': lon or (self.cfg.get('map_center') or [30.6948, 103.8508])[1],
                            'limitationsGoalsSexInfoId': d.get('limitationsGoalsSexInfoId') or '',
                            'patternId': d.get('patternId') or '',
                            'scoringType': d.get('scoringType') or 1,
                            'semesterId': sem})
                    if rng:
                        merged = dict(d)
                        for k in ('rangeRunningRegion', 'signPoint',
                                  'signRunningRegion', 'scopePattern',
                                  'fixedPointPattern'):
                            if k in rng:
                                merged[k] = rng[k]
                        d = merged
                        self.log.ok('围栏已拉取: %d 组' % len(
                            d.get('rangeRunningRegion') or []))

                self.ruleset = R.RuleSet(d)
                CFG.save_json(CFG.RULES_FILE, d)
                self.log.ok('规则: hasRule=%s 配速 %s~%s 打卡 %d 围栏 %d'
                            % (d.get('hasRule'),
                               self.ruleset.pace_min, self.ruleset.pace_max,
                               len(self.ruleset.sign_points),
                               len(self.ruleset.fence)))
                if on_done:
                    on_done(True, d)
            except Exception as e:
                self.log.error('拉规则失败: %s' % e)
                if on_done:
                    on_done(False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    # ---- 明文小工具（实测这些接口接受明文，不走 envelope）----
    def _headers(self):
        return {'Content-Type': 'application/json; charset=UTF-8',
                'User-Agent': 'okhttp/4.9.3',
                'Authorization': 'Bearer ' + self.session.access_token,
                'Organization': str(self.session.school_id)}

    def _get_plain(self, path):
        import urllib.request, urllib.error
        req = urllib.request.Request(BU.BASE + path, headers=self._headers(),
                                     method='GET')
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode('utf-8', 'replace'))
            except Exception:
                return None

    def _post_plain(self, path, obj):
        import urllib.request, urllib.error
        req = urllib.request.Request(
            BU.BASE + path,
            data=json.dumps(obj, ensure_ascii=False).encode('utf-8'),
            headers=self._headers(), method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                o = json.loads(r.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            try:
                o = json.loads(e.read().decode('utf-8', 'replace'))
            except Exception:
                return None
        except Exception:
            return None
        d = o.get('data')
        if isinstance(d, dict) and 'pyd' in d:
            try:
                d = json.loads(LE.unwrap_response(d))
            except Exception:
                pass
        return d if isinstance(d, dict) else None

    def _fetch_semester_sync(self):
        o = self._get_plain('education/semester/queryAll')
        sems = (o or {}).get('data') or []
        cur = [s for s in sems if s.get('current') == 1]
        pick = (cur or sems)
        if not pick:
            return False, None
        sem_id = pick[-1].get('id')
        self.cfg.set('semester_id', sem_id)
        self.cfg.save()
        return bool(sem_id), sem_id

    def load_cached_rules(self):
        d = CFG.load_json(CFG.RULES_FILE)
        if d:
            self.ruleset = R.RuleSet(d)
            return self.ruleset
        return None

    # ------------------------------------------------------------------
    # 生成轨迹
    # ------------------------------------------------------------------
    def build_track(self, waypoints, pace=None, duration=None, seed=None):
        """返回 (vo, sim_points, stats)。"""
        if not waypoints or len(waypoints) < 3:
            raise ValueError('跑道至少需要 3 个顶点（当前 %d 个）'
                             % (len(waypoints) if waypoints else 0))

        # 跑道长度检查
        loop_len = 0.0
        n = len(waypoints)
        for i in range(n):
            a = waypoints[i]
            b = waypoints[(i + 1) % n]
            loop_len += run_sim.haversine(a[0], a[1], b[0], b[1])
        if loop_len < 50:
            raise ValueError('跑道太短（周长 %.0f 米），'
                             '请把顶点拉开一些' % loop_len)

        pace = pace or self.cfg.get('pace')
        duration = duration or self.cfg.get('duration')
        sim = run_sim.TrackSim(
            waypoints, float(pace), int(duration),
            seed=seed if seed is not None else int(time.time()) % 100000,
            gps_noise=float(self.cfg.get('noise')),
            drop_rate=float(self.cfg.get('drop')),
            src_crs='gcj02')
        pts, dropped = sim.generate()

        total = 0.0
        for i in range(1, len(pts)):
            total += run_sim.haversine(pts[i - 1][1], pts[i - 1][2],
                                       pts[i][1], pts[i][2])
        keep = int(pts[-1][0]) if pts else 0

        # 打卡点
        sign_targets = []
        if self.ruleset and self.ruleset.sign_points:
            sign_targets = list(self.ruleset.sign_points)
        elif self.cfg.get('sign_mode') == 'all':
            sign_targets = list(sim.wp)
        elif self.cfg.get('sign_mode') == 'alt':
            sign_targets = list(sim.wp[::2])

        # type 跟随账号实际规则（与真机一致）：
        #   有围栏规则 -> '范围跑'；无规则 -> '自由跑'（真机在 hasRule=false 时
        #   同样传 lgs=''，见 RunningViewModel.n()）
        rs = self.ruleset
        if rs and rs.has_rule and rs.fence:
            run_type = '范围跑'
        elif rs and rs.has_rule and rs.sign_points:
            run_type = '定点跑'
        else:
            run_type = '自由跑'

        vo = run_sim.build_vo((pts, dropped), {
            'start_ms': int(time.time() * 1000) - keep * 1000,   # 过去开始，现在结束
            'lgs_id': self.cfg.get('lgs_id') or self.session.lgs_id or (rs.lgs_id if rs else '') or '',
            'semester_id': self.cfg.get('semester_id') or self.session.semester_id or '0',
            'scoring_type': self.cfg.get('scoring_type') or '1',
            'sign_targets': sign_targets,
            # 真实 App 字段语义（反编译确认）
            'type': run_type,
            'weight': float(self.session.raw.get('data', {}).get('weight')
                            or self.cfg.get('weight') or 63.0),
            'cadence': float(self.cfg.get('cadence') or 172.0),
            'pace_range': float(self.session.pace_range or 0),
        })

        stats = {
            'points': len(pts),
            'dropped': dropped,
            'mileage_m': total,
            'keep_s': keep,
            'pace': (keep / total * 1000) if total else 0,   # s/km 展示用
            'sign_count': len(vo.get('signPoint') or []),
        }
        return vo, pts, stats

    # ------------------------------------------------------------------
    # 体检
    # ------------------------------------------------------------------
    def check(self, vo):
        if not self.ruleset:
            return True, [], ['未加载规则，跳过体检']
        return self.ruleset.check(vo)

    # ------------------------------------------------------------------
    # 上传（真实账号实测打通：明文 JSON，时间字段为格式化字符串）
    # ------------------------------------------------------------------
    def upload_ready(self):
        """上传始终可用（明文接口，已实测 code=0）。"""
        return self.session.valid

    def do_upload(self, vo, start_ms=None, end_ms=None, on_progress=None):
        """同步执行上传（调用方放后台线程）。"""
        school = self.cfg.get('school_id') or self.session.school_id
        r = uploader.upload(self.session.access_token, school, vo)
        return r

    def upload(self, vo, on_done=None, on_log=None):
        """异步上传（后台线程），成功失败都记历史。"""
        def worker():
            try:
                if not self.session.valid:
                    if on_done:
                        on_done(False, '未登录')
                    return

                ok, probs, warns = self.check(vo)
                for w in warns:
                    self.log.warn(w)
                if probs and not self.cfg.get('force_upload'):
                    for p in probs:
                        self.log.error('体检: ' + p)
                    if on_done:
                        on_done(False, '体检未通过：' + probs[0])
                    return

                if on_log:
                    on_log('正在上传…')
                r = self.do_upload(vo)
                raw_m = (vo.get('totalMileage') or 0)
                km = raw_m if raw_m < 100 else raw_m / 1000.0   # 新语义=km
                ap = (vo.get('avePace') or 0)
                pace = ap / 1000.0 if ap > 10000 else ap        # ms/km -> s/km
                if r.get('ok'):
                    self.log.ok('上传成功 [%s]: %s'
                                % (r.get('mode'), r.get('message') or 'ok'))
                    self.history.add(True, km, pace, 'ok',
                                     {'mode': r.get('mode')})
                    if on_done:
                        on_done(True, r.get('message') or '上传成功')
                else:
                    self.log.error('上传被拒 [%s] code=%s %s'
                                   % (r.get('mode'), r.get('code'),
                                      r.get('message')))
                    self.history.add(False, km, pace,
                                     str(r.get('message'))[:80])
                    if on_done:
                        on_done(False, str(r.get('message')))
            except Exception as e:
                self.log.error('上传异常: %s' % e)
                if on_done:
                    on_done(False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # 一键跑
    # ------------------------------------------------------------------
    def run_once(self, waypoints, on_progress=None, on_done=None):
        def emit(stage, msg):
            self.log.info('[%s] %s' % (stage, msg))
            if on_progress:
                on_progress(stage, msg)

        def worker():
            try:
                emit('准备', '生成轨迹')
                vo, pts, st = self.build_track(waypoints)
                km = st['mileage_m'] / 1000.0
                emit('生成', '里程 %.2f km  配速 %.0f s/km  采样 %d'
                     % (km, st['pace'], st['points']))

                # 本地配额检查（防封号）
                qok, qreason = self.history.check_quota(km, self.cfg)
                if not qok and not self.cfg.get('force_upload'):
                    emit('配额', '拦下: ' + qreason)
                    self.history.add(False, km, st['pace'],
                                     '配额拦下: ' + qreason)
                    if on_done:
                        on_done(False, qreason, vo, pts, st)
                    return
                if not qok:
                    emit('配额', '警告: ' + qreason + '（已强制继续）')
                else:
                    emit('配额', '今日已跑 %.2f km，本次 %.2f km，通过'
                         % (self.history.today_km(), km))

                ok, probs, warns = self.check(vo)
                for w in warns:
                    emit('体检', w)
                if probs:
                    for p in probs:
                        emit('体检', '问题: ' + p)
                    if not self.cfg.get('force_upload'):
                        self.history.add(False, km, st['pace'],
                                         '体检未通过: ' + probs[0])
                        if on_done:
                            on_done(False, '体检未通过', vo, pts, st)
                        return
                else:
                    emit('体检', '通过')

                # 注意：vo['startTime'] 是 'yyyy-MM-dd HH:mm:ss' 字符串，不能 int()
                emit('上传', '正在提交')
                r = self.do_upload(vo)
                if r.get('ok'):
                    emit('完成', '上传成功 [%s]' % r.get('mode'))
                    self.history.add(True, km, st['pace'],
                                     r.get('message') or 'ok',
                                     {'mode': r.get('mode')})
                    if on_done:
                        on_done(True, r.get('message') or 'ok', vo, pts, st)
                else:
                    emit('失败', 'code=%s %s' % (r.get('code'),
                                                 r.get('message')))
                    self.history.add(False, km, st['pace'],
                                     str(r.get('message'))[:80])
                    if on_done:
                        on_done(False, str(r.get('message')), vo, pts, st)
            except Exception as e:
                self.log.error('执行异常: %s' % e)
                self.log.error(traceback.format_exc()[-500:])
                try:
                    self.history.add(False, 0, 0, '异常: %s' % e)
                except Exception:
                    pass
                if on_done:
                    on_done(False, str(e), None, None, None)

        threading.Thread(target=worker, daemon=True).start()
