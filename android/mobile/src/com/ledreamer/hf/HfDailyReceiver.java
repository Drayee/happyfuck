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

    @Override
    public void onReceive(Context ctx, Intent it) {
        try {
            if (ctx == null) return;
            Context c = ctx.getApplicationContext();
            HfLog.init(c);
            String action = it == null ? null : it.getAction();

            if (HfAutoRun.ACTION_START_NOW.equals(action)) {
                // 用户点了通知
                HfLog.i(TAG, "user tapped start");
                boolean ok = HfAutoRun.startRun(c);
                if (!ok) {
                    HfScheduler.postResultNotification(c, "启动失败，请手动打开 App 跑一次");
                }
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
                boolean ok = HfAutoRun.startRun(c);
                if (!ok) {
                    // 全自动被拦，降级为通知
                    HfScheduler.postStartNotification(c);
                }
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
