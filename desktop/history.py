#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 上传历史与配额。

记录每次上传，据此判断：
  - 今天已经跑了多少公里（日配额）
  - 距上次多久（最小间隔）
  - 连续失败次数（触发告警）
"""
import json
import os
from datetime import datetime, date, timedelta

import config as CFG

HISTORY_FILE = os.path.join(CFG.DATA_DIR, 'history.json')


class History:
    def __init__(self):
        self.records = CFG.load_json(HISTORY_FILE, []) or []

    def save(self):
        # 只留最近 500 条
        if len(self.records) > 500:
            self.records = self.records[-500:]
        CFG.save_json(HISTORY_FILE, self.records)

    # ------------------------------------------------------------------
    def add(self, ok, km, pace, msg='', extra=None):
        rec = {
            'ts': datetime.now().isoformat(timespec='seconds'),
            'date': date.today().isoformat(),
            'ok': bool(ok),
            'km': round(float(km), 3),
            'pace': round(float(pace), 1),
            'msg': msg or '',
        }
        if extra:
            rec.update(extra)
        self.records.append(rec)
        self.save()
        return rec

    # ------------------------------------------------------------------
    def today_km(self):
        """今天成功的总里程（只算成功上传的）。"""
        d = date.today().isoformat()
        return sum(r.get('km', 0) for r in self.records
                   if r.get('date') == d and r.get('ok'))

    def today_count(self):
        d = date.today().isoformat()
        return sum(1 for r in self.records
                   if r.get('date') == d and r.get('ok'))

    def week_km(self):
        start = date.today() - timedelta(days=date.today().weekday())
        return sum(r.get('km', 0) for r in self.records
                   if r.get('ok') and r.get('date', '') >= start.isoformat())

    def last_ok(self):
        for r in reversed(self.records):
            if r.get('ok'):
                return r
        return None

    def last_any(self):
        return self.records[-1] if self.records else None

    def hours_since_last(self):
        r = self.last_ok()
        if not r:
            return None
        try:
            t = datetime.fromisoformat(r['ts'])
            return (datetime.now() - t).total_seconds() / 3600.0
        except Exception:
            return None

    def consecutive_fails(self):
        n = 0
        for r in reversed(self.records):
            if r.get('ok'):
                break
            n += 1
        return n

    def recent(self, n=20):
        return list(reversed(self.records[-n:]))

    # ------------------------------------------------------------------
    def check_quota(self, km, cfg):
        """上传前配额检查，返回 (ok, reason)。

        这是本地保护，不是服务端规则，目的是避免异常行为。
        """
        daily_max = float(cfg.get('max_daily_km') or 0)
        if daily_max > 0:
            used = self.today_km()
            if used + km > daily_max:
                return False, ('超出每日上限：今天已跑 %.2f km，'
                               '本次 %.2f km，上限 %.2f km'
                               % (used, km, daily_max))

        min_h = float(cfg.get('min_interval_hours') or 0)
        if min_h > 0:
            gap = self.hours_since_last()
            if gap is not None and gap < min_h:
                return False, ('距上次仅 %.1f 小时，'
                               '要求间隔 ≥ %.0f 小时' % (gap, min_h))

        fails = self.consecutive_fails()
        if fails >= 3:
            return False, ('已连续失败 %d 次，先排查问题再继续' % fails)

        return True, ''

    def stats(self):
        """给界面用的汇总。"""
        return {
            'today_km': self.today_km(),
            'today_count': self.today_count(),
            'week_km': self.week_km(),
            'hours_since': self.hours_since_last(),
            'fails': self.consecutive_fails(),
            'total': len(self.records),
        }
