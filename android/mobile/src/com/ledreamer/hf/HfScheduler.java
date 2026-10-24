package com.ledreamer.hf;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

import java.util.Calendar;

/**
 * 每日自动刷课 —— 闹钟与通知。
 */
public class HfScheduler {

    private static final String TAG = "HF_SCHED";
    public static final int REQ_ALARM = 7001;
    public static final String CHANNEL = "hf_auto";
    public static final int NOTI_START = 7002;
    public static final int NOTI_RESULT = 7003;

    // =====================================================================
    // 闹钟
    // =====================================================================

    public static void schedule(Context c) {
        schedule(c, true);
    }

    /**
     * @param allowToday true = 今天的时间还没过就排今天，否则排明天
     */
    public static void schedule(Context c, boolean allowToday) {
        try {
            cancel(c);
            if (!HfAutoRun.isEnabled(c)) {
                HfLog.i(TAG, "disabled, no alarm");
                return;
            }
            Calendar t = nextTrigger(c, allowToday);
            AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
            if (am == null) return;
            PendingIntent pi = alarmIntent(c);
            long ms = t.getTimeInMillis();
            try {
                if (Build.VERSION.SDK_INT >= 23) {
                    am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, ms, pi);
                } else {
                    am.setExact(AlarmManager.RTC_WAKEUP, ms, pi);
                }
            } catch (Throwable noExact) {
                HfLog.w(TAG, "exact alarm denied, fallback to inexact: " + noExact);
                am.set(AlarmManager.RTC_WAKEUP, ms, pi);
            }
            HfLog.i(TAG, "scheduled at " + t.getTime()
                    + " mode=" + HfAutoRun.getMode(c));
        } catch (Throwable t) {
            HfLog.e(TAG, "schedule err: " + t, t);
        }
    }

    public static void cancel(Context c) {
        try {
            AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
            if (am != null) am.cancel(alarmIntent(c));
        } catch (Throwable ignore) { }
    }

    private static Calendar nextTrigger(Context c, boolean allowToday) {
        Calendar now = Calendar.getInstance();
        Calendar t = (Calendar) now.clone();
        t.set(Calendar.HOUR_OF_DAY, HfAutoRun.getHour(c));
        t.set(Calendar.MINUTE, HfAutoRun.getMinute(c));
        t.set(Calendar.SECOND, 0);
        t.set(Calendar.MILLISECOND, 0);
        if (!allowToday || !t.after(now)) {
            t.add(Calendar.DAY_OF_YEAR, 1);
        }
        return t;
    }

    private static PendingIntent alarmIntent(Context c) {
        Intent it = new Intent(c, HfDailyReceiver.class);
        it.setAction(HfDailyReceiver.ACTION_ALARM);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getBroadcast(c, REQ_ALARM, it, flags);
    }

    // =====================================================================
    // 通知
    // =====================================================================

    public static void ensureChannel(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = (NotificationManager)
                c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (nm.getNotificationChannel(CHANNEL) != null) return;
        NotificationChannel ch = new NotificationChannel(
                CHANNEL, "每日跑步", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("到点提醒开始今日跑步");
        ch.enableVibration(true);
        nm.createNotificationChannel(ch);
    }

    /** 半自动：发一条「点我开始跑步」的通知。 */
    public static void postStartNotification(Context c) {
        try {
            ensureChannel(c);
            NotificationManager nm = (NotificationManager)
                    c.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;

            Intent start = new Intent(c, HfDailyReceiver.class);
            start.setAction(HfAutoRun.ACTION_START_NOW);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
            PendingIntent pi = PendingIntent.getBroadcast(c, 7004, start, flags);

            Notification.Builder b = Build.VERSION.SDK_INT >= 26
                    ? new Notification.Builder(c, CHANNEL)
                    : new Notification.Builder(c);
            b.setSmallIcon(android.R.drawable.ic_menu_mylocation)
             .setContentTitle("今日跑步待开始")
             .setContentText("点此开始自动跑（目标 "
                     + HfAutoRun.getTargetKm(c) + " km）")
             .setAutoCancel(true)
             .setContentIntent(pi);
            nm.notify(NOTI_START, b.build());
            HfLog.i(TAG, "start notification posted");
        } catch (Throwable t) {
            HfLog.e(TAG, "postStartNotification err: " + t, t);
        }
    }

    /** 结果/异常通知。 */
    public static void postResultNotification(Context c, String text) {
        try {
            ensureChannel(c);
            NotificationManager nm = (NotificationManager)
                    c.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            Notification.Builder b = Build.VERSION.SDK_INT >= 26
                    ? new Notification.Builder(c, CHANNEL)
                    : new Notification.Builder(c);
            b.setSmallIcon(android.R.drawable.ic_dialog_info)
             .setContentTitle("每日跑步")
             .setContentText(text)
             .setAutoCancel(true);
            nm.notify(NOTI_RESULT, b.build());
        } catch (Throwable t) {
            HfLog.e(TAG, "postResultNotification err: " + t, t);
        }
    }
}
