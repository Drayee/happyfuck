package com.ledreamer.hf;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * 开机 / 应用更新后重排闹钟（AlarmManager 的闹钟在重启后会丢）。
 */
public class HfBootReceiver extends BroadcastReceiver {

    private static final String TAG = "HF_BOOT";

    @Override
    public void onReceive(Context ctx, Intent it) {
        try {
            if (ctx == null) return;
            Context c = ctx.getApplicationContext();
            HfLog.init(c);
            String a = it == null ? "" : it.getAction();
            HfLog.i(TAG, "boot event: " + a);
            if (HfAutoRun.isEnabled(c)) {
                HfScheduler.schedule(c, true);
            }
        } catch (Throwable t) {
            HfLog.e(TAG, "onReceive err: " + t, t);
        }
    }
}
