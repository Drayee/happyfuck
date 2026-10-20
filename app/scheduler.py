#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 定时调度器。

特性：
  - 每日多个时间点
  - ±N 分钟随机抖动（避免每天同一秒上传）
  - 指定星期几
  - 最小间隔保护
  - 日里程配额
"""
import random
import threading
import time
from datetime import datetime, timedelta


class Scheduler:
    def __init__(self, service, cfg, on_fire=None, on_log=None):
        self.svc = service
        self.cfg = cfg
        self.on_fire = on_fire
        self.on_log = on_log or (lambda m: None)

        self._thread = None
        self._stop = threading.Event()
        self._next_at = None
        self._next_desc = ''
        self._last_fire = None
        self._fired_today = {}      # 'HH:MM' -> date

    # ------------------------------------------------------------------
    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def next_at(self):
        return self._next_at

    @property
    def next_desc(self):
        return self._next_desc

    @property
    def last_fire(self):
        return self._last_fire

    # ------------------------------------------------------------------
    def start(self):
        if self.running:
            return False

        # 启动前校验配置，避免空转
        times = self.cfg.get('schedule_times') or []
        days = self.cfg.get('schedule_days') or []
        if not times:
            self.on_log('启动失败：没有设置任何时间点')
            return False
        if not days:
            self.on_log('启动失败：没有选择任何执行星期')
            return False

        # 校验时间格式
        valid = 0
        for t in times:
            try:
                hh, mm = [int(x) for x in str(t).split(':')[:2]]
                if 0 <= hh < 24 and 0 <= mm < 60:
                    valid += 1
            except Exception:
                pass
        if valid == 0:
            self.on_log('启动失败：时间点格式都不对（应为 HH:MM）')
            return False

        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.on_log('调度已启动（%d 个时间点，%d 天）' % (valid, len(days)))
        return True

    def stop(self):
        if not self.running:
            return False
        self._stop.set()
        self.on_log('调度已停止')
        return True

    # ------------------------------------------------------------------
    def _candidates_today(self):
        """今天所有候选触发时刻（含抖动）。"""
        times = self.cfg.get('schedule_times') or []
        jitter = int(self.cfg.get('schedule_jitter_min') or 0)
        days = self.cfg.get('schedule_days') or [1, 2, 3, 4, 5, 6, 7]
        now = datetime.now()

        if now.isoweekday() not in days:
            return []

        out = []
        for t in times:
            try:
                hh, mm = [int(x) for x in str(t).split(':')[:2]]
            except Exception:
                continue
            base = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if jitter > 0:
                base += timedelta(minutes=random.randint(-jitter, jitter))
            key = '%02d:%02d' % (hh, mm)
            # 今天这个时间点是否已经跑过
            if self._fired_today.get(key) == now.date():
                continue
            if base <= now:
                continue
            out.append((base, key))
        out.sort()
        return out

    def _compute_next(self):
        """算出下一次触发时刻。"""
        # 今天剩下的
        cand = self._candidates_today()
        if cand:
            return cand[0]

        # 今天没了，找明天起 7 天内第一个匹配的
        times = self.cfg.get('schedule_times') or []
        jitter = int(self.cfg.get('schedule_jitter_min') or 0)
        days = self.cfg.get('schedule_days') or [1, 2, 3, 4, 5, 6, 7]
        now = datetime.now()

        best = None
        for delta in range(1, 8):
            d = now + timedelta(days=delta)
            if d.isoweekday() not in days:
                continue
            for t in times:
                try:
                    hh, mm = [int(x) for x in str(t).split(':')[:2]]
                except Exception:
                    continue
                base = d.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if jitter > 0:
                    base += timedelta(minutes=random.randint(-jitter, jitter))
                key = '%02d:%02d' % (hh, mm)
                if best is None or base < best[0]:
                    best = (base, key)
            if best:
                break
        return best

    # ------------------------------------------------------------------
    def _loop(self):
        while not self._stop.is_set():
            try:
                nxt = self._compute_next()
                if not nxt:
                    self._next_at = None
                    self._next_desc = '无可用时间点'
                    self._stop.wait(60)
                    continue

                when, key = nxt
                self._next_at = when
                left = (when - datetime.now()).total_seconds()
                self._next_desc = '%s（%d 分后）' % (
                    when.strftime('%m-%d %H:%M'), max(0, int(left / 60)))

                # 分段等待，便于及时响应停止
                while left > 0 and not self._stop.is_set():
                    step = min(30.0, left)
                    if self._stop.wait(step):
                        break
                    left = (when - datetime.now()).total_seconds()
                    self._next_desc = '%s（%d 分后）' % (
                        when.strftime('%m-%d %H:%M'), max(0, int(left / 60)))

                if self._stop.is_set():
                    break
                if datetime.now() < when:
                    continue

                # 最小间隔保护
                min_h = float(self.cfg.get('min_interval_hours') or 0)
                if self._last_fire and min_h > 0:
                    gap = (datetime.now() - self._last_fire).total_seconds() / 3600
                    if gap < min_h:
                        self.on_log('跳过：距上次仅 %.1f 小时（要求 ≥ %.0f）'
                                    % (gap, min_h))
                        self._fired_today[key] = datetime.now().date()
                        continue

                self._fired_today[key] = datetime.now().date()
                self._last_fire = datetime.now()
                self.on_log('触发定时任务 %s' % key)
                if self.on_fire:
                    try:
                        self.on_fire()
                    except Exception as e:
                        self.on_log('触发回调异常: %s' % e)

            except Exception as e:
                self.on_log('调度循环异常: %s' % e)
                self._stop.wait(30)
