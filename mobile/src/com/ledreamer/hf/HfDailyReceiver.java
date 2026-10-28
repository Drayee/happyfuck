package com.ledreamer.hf;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * 每日定时触发。
 *
 * 半自动（MODE_NOTIFY）：到点发通知，用户点一下开跑
 * 全自动（MODE_AUTO）  ：到点直接 startActivity 拉跑步页
 *                        失败（后台启动被系统拦）自动降级为通知
 */
public class HfDailyReceiver extends BroadcastReceiver {

    private static final String TAG = "HF_ALARM";
    public static final String ACTION_ALARM = "com.ledreamer.hf.ACTION_ALARM";

    /**
     * 后台线程里先查学期再开跑：
     * - 学期变了 -> 跳过并通知（避免用过期规则跑出无效记录）
     * - 查不到（网络/token）-> 按缓存规则继续
     * 用 goAsync() 保活，避免 onReceive 返回后进程被回收。
     */
    private void startWithSemesterCheck(final Context c) {
        final PendingResult pr = goAsync();
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    String msg = HfAutoRun.checkAndStart(c);
                    if (msg != null) {
                        HfScheduler.postResultNotification(c, msg);
                    }
                } catch (Throwable t) {
                    HfLog.e(TAG, "auto start err", t);
                    HfScheduler.postResultNotification(c, "自动跑启动异常，请手动跑一次");
                } finally {
                    try { pr.finish(); } catch (Throwable ignore) { }
                }
            }
        }).start();
    }

    @Override
    public void onReceive(Context ctx, Intent it) {
        try {
            if (ctx == null) return;
            Context c = ctx.getApplicationContext();
            HfLog.init(c);
            String action = it == null ? null : it.getAction();

            if (HfAutoRun.ACTION_START_NOW.equals(action)) {
                // 用户点了通知：同样先查学期，避免用过期规则跑
                HfLog.i(TAG, "user tapped start");
                startWithSemesterCheck(c);
                return;
            }

            if (!ACTION_ALARM.equals(action)) return;

            // ① 今天跑过就跳过
            String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US)
                    .format(new Date());
            if (today.equals(HfAutoRun.getLastRunDate(c))) {
                HfLog.i(TAG, "already ran today, skip");
                HfScheduler.schedule(c, false);
                return;
            }

            // ② 开关关着就不跑
            if (!HfAutoRun.isEnabled(c)) {
                HfLog.i(TAG, "disabled, skip");
                return;
            }

            // ③ 没有缓存的 extras，只能提醒
            if (!HfAutoRun.hasCapturedExtras(c)) {
                HfLog.w(TAG, "no cached extras");
                HfScheduler.postResultNotification(c,
                        "还没有跑过一次，请先手动跑一次以初始化");
                HfScheduler.schedule(c, false);
                return;
            }

            // ④ 按模式触发
            String mode = HfAutoRun.getMode(c);
            if (HfAutoRun.MODE_AUTO.equals(mode)) {
                startWithSemesterCheck(c);
            } else {
                HfScheduler.postStartNotification(c);
            }

            // ⑤ 无论如何排明天（多排一次，出错也能继续）
            HfScheduler.schedule(c, false);
        } catch (Throwable t) {
            HfLog.e(TAG, "onReceive err: " + t, t);
        }
    }
}
