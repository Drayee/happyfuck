package com.ledreamer.hf;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Parcel;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.lang.ref.WeakReference;
import java.math.BigDecimal;

/**
 * 每日自动刷课 —— 核心。
 *
 * 设计要点：
 *  - 开始跑步只需要 3 个 Intent extra（serRuleCondition / userInfo / rangeLatLngJson）
 *  - 这三样是 Parcelable / String，没法手搓，所以「学一次、回放 N 次」：
 *      第一次真实跑步时 captureIntentExtras() 把它们序列化到 hf_intent.bin
 *      之后每天 unmarshall 回放
 *  - 结束上传：反射调用 RunningActivity.S()（public final），跳过「确认结束」弹窗
 *
 * 两种模式（设置里可切）：
 *  - MODE_NOTIFY  半自动：到点发通知，用户点一下开跑
 *  - MODE_AUTO    全自动：到点直接拉起 Activity（需悬浮窗/后台弹出权限）
 */
public class HfAutoRun {

    private static final String TAG = "HF_AUTO";
    private static final String PREF = "hf_auto";
    private static final String INTENT_BIN = "hf_intent.bin";

    public static final String MODE_NOTIFY = "notify";
    public static final String MODE_AUTO = "auto";

    public static final String ACTION_START_NOW =
            "com.ledreamer.hf.ACTION_START_NOW";

    /** 目标距离（公里），默认 3.5 */
    public static final float DEFAULT_TARGET_KM = 3.5f;

    private static WeakReference<Activity> runningActivity = new WeakReference<Activity>(null);
    private static boolean finishTriggered = false;
    /** 是否由「自动跑」拉起的这一场。手动跑不武装，避免误伤。 */
    private static boolean armed = false;
    /** 兜底读数只告警一次 */
    private static boolean fallbackWarned = false;

    public static void arm() {
        armed = true;
        finishTriggered = false;
    }

    public static void disarm() {
        armed = false;
    }

    /** armed 持久化：进程被杀后重建跑步页时还能继续收尾 */
    private static void persistArmed(Context c, boolean v) {
        try {
            prefs(c).edit().putBoolean("armed", v).apply();
        } catch (Throwable ignore) { }
    }

    private static boolean persistedArmed(Context c) {
        try {
            return prefs(c).getBoolean("armed", false);
        } catch (Throwable t) {
            return false;
        }
    }

    public static boolean isArmed() {
        return armed;
    }

    // =====================================================================
    // 配置
    // =====================================================================

    private static SharedPreferences prefs(Context c) {
        return c.getApplicationContext().getSharedPreferences(PREF, Context.MODE_PRIVATE);
    }

    public static boolean isEnabled(Context c) {
        return prefs(c).getBoolean("enabled", false);
    }

    public static void setEnabled(Context c, boolean v) {
        prefs(c).edit().putBoolean("enabled", v).apply();
    }

    public static int getHour(Context c) {
        return prefs(c).getInt("hour", 6);
    }

    public static int getMinute(Context c) {
        return prefs(c).getInt("minute", 30);
    }

    public static void setTime(Context c, int h, int m) {
        prefs(c).edit().putInt("hour", h).putInt("minute", m).apply();
    }

    public static String getMode(Context c) {
        return prefs(c).getString("mode", MODE_NOTIFY);
    }

    public static void setMode(Context c, String mode) {
        prefs(c).edit().putString("mode", mode).apply();
    }

    public static float getTargetKm(Context c) {
        return prefs(c).getFloat("targetKm", DEFAULT_TARGET_KM);
    }

    public static void setTargetKm(Context c, float km) {
        prefs(c).edit().putFloat("targetKm", km).apply();
    }

    public static String getLastRunDate(Context c) {
        return prefs(c).getString("lastRunDate", "");
    }

    public static void setLastRunDate(Context c, String d) {
        prefs(c).edit().putString("lastRunDate", d).apply();
    }

    // =====================================================================
    // Intent extras 捕获 / 回放
    // =====================================================================

    /** 在 RunningActivity.initData() 开头调用：把本次真实跑步的 extras 存盘。 */
    public static void captureIntentExtras(Context ctx, Intent it) {
        if (ctx == null || it == null) return;
        try {
            Bundle src = new Bundle();
            src.putParcelable("serRuleCondition", it.getParcelableExtra("serRuleCondition"));
            src.putParcelable("userInfo", it.getParcelableExtra("userInfo"));
            String fenceJson = it.getStringExtra("rangeLatLngJson");

            if (src.getParcelable("serRuleCondition") == null
                    || src.getParcelable("userInfo") == null) {
                HfLog.i(TAG, "capture skipped: missing parcelables");
                return;
            }

            Parcel p = Parcel.obtain();
            try {
                src.writeToParcel(p, 0);
                byte[] raw = p.marshall();
                File f = new File(ctx.getApplicationContext().getFilesDir(), INTENT_BIN);
                FileOutputStream out = new FileOutputStream(f, false);
                out.write(raw);
                out.close();
                prefs(ctx).edit()
                        .putString("rangeLatLngJson", fenceJson == null ? "" : fenceJson)
                        .apply();
                HfLog.i(TAG, "captured extras: " + raw.length + " bytes, fenceJson="
                        + (fenceJson == null ? 0 : fenceJson.length()));
            } finally {
                p.recycle();
            }
        } catch (Throwable t) {
            HfLog.e(TAG, "captureIntentExtras err: " + t, t);
        }
    }

    public static boolean hasCapturedExtras(Context c) {
        File f = new File(c.getApplicationContext().getFilesDir(), INTENT_BIN);
        return f.exists() && f.length() > 0;
    }

    private static Bundle loadExtras(Context c) {
        try {
            File f = new File(c.getApplicationContext().getFilesDir(), INTENT_BIN);
            if (!f.exists() || f.length() <= 0) return null;
            byte[] raw = new byte[(int) f.length()];
            FileInputStream in = new FileInputStream(f);
            int off = 0;
            while (off < raw.length) {
                int n = in.read(raw, off, raw.length - off);
                if (n <= 0) break;
                off += n;
            }
            in.close();
            Parcel p = Parcel.obtain();
            Bundle b;
            try {
                p.unmarshall(raw, 0, raw.length);
                p.setDataPosition(0);
                b = p.readBundle(HfAutoRun.class.getClassLoader());
            } finally {
                p.recycle();
            }
            if (b != null) b.setClassLoader(HfAutoRun.class.getClassLoader());
            return b;
        } catch (Throwable t) {
            HfLog.e(TAG, "loadExtras err: " + t, t);
            return null;
        }
    }

    // =====================================================================
    // 启动跑步
    // =====================================================================

    public static final String RUN_ACTIVITY =
            "com.ledreamer.zz.activity.running.RangeRunningActivity";

    /** 组好一条可以直接拉起跑步页的 Intent；失败返回 null。 */
    public static Intent buildRunIntent(Context c) {
        Bundle b = loadExtras(c);
        if (b == null) {
            HfLog.w(TAG, "no cached extras, run once manually first");
            return null;
        }
        if (b.getParcelable("serRuleCondition") == null
                || b.getParcelable("userInfo") == null) {
            HfLog.w(TAG, "cached extras incomplete");
            return null;
        }
        Intent it = new Intent();
        it.setClassName(c.getPackageName(), RUN_ACTIVITY);
        android.os.Parcelable rc = b.getParcelable("serRuleCondition");
        android.os.Parcelable ui = b.getParcelable("userInfo");
        it.putExtra("serRuleCondition", rc);
        it.putExtra("userInfo", ui);
        String fenceJson = prefs(c).getString("rangeLatLngJson", "");
        if (fenceJson != null && fenceJson.length() > 0) {
            it.putExtra("rangeLatLngJson", fenceJson);
        }
        it.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return it;
    }

    /**
     * 拉起跑步页。
     * @return true = 已发出 startActivity
     */
    /**
     * 上传链路需要 UniversityApplication.a（companion 的 d()）。
     * 这个静态字段**只有 uni-app 流程（UniAppViewModel）会赋值**；
     * 自动跑直接拉起 RangeRunningActivity 绕过了 uni-app，
     * 冷启动时它是 null，于是 RunningViewModel.i() 命中
     *   if (UniversityApplication.INSTANCE.d() == null) { 提示"没有用户数据"; }   ← 静默不上传
     *
     * 这里用我们缓存的 userInfo（hf_intent.bin 里那个）把它补上。
     */
    private static boolean ensureAppUserInfo(Context c) {
        try {
            Class<?> ua = Class.forName("com.ledreamer.zz.UniversityApplication");
            java.lang.reflect.Field f = ua.getField("a");
            Object cur = f.get(null);
            if (cur != null) {
                HfLog.i(TAG, "app userInfo already present");
                return true;
            }
            Bundle b = loadExtras(c);
            if (b == null) {
                HfLog.w(TAG, "ensureUserInfo: 没有缓存的参数");
                return false;
            }
            Object ui = b.getParcelable("userInfo");
            if (ui == null) {
                HfLog.w(TAG, "ensureUserInfo: 缓存的 userInfo 为空");
                return false;
            }
            f.set(null, ui);
            HfLog.i(TAG, "app userInfo injected from cache -> " + ui.getClass().getSimpleName());
            return true;
        } catch (Throwable t) {
            HfLog.e(TAG, "ensureUserInfo err: " + t, t);
            return false;
        }
    }

    public static boolean startRun(Context c) {
        Intent it = buildRunIntent(c);
        if (it == null) return false;
        if (runningActivity.get() != null) {
            HfLog.w(TAG, "已有跑步页在运行，跳过重复启动");
            return false;
        }
        try {
            finishTriggered = false;
            armed = true;
            persistArmed(c, true);
            ensureAppUserInfo(c);          // 否则上传会因 d()==null 被静默拒绝
            c.getApplicationContext().startActivity(it);
            HfLog.i(TAG, "startRun ok (armed)");
            return true;
        } catch (Throwable t) {
            HfLog.e(TAG, "startRun failed (后台启动被系统拦截？): " + t, t);
            return false;
        }
    }

    // =====================================================================
    // Activity 跟踪 + 自动收尾
    // =====================================================================

    public static void installActivityTracker(Context ctx) {
        try {
            if (!(ctx instanceof Application)) return;
            ((Application) ctx).registerActivityLifecycleCallbacks(
                    new Application.ActivityLifecycleCallbacks() {
                @Override
                public void onActivityCreated(Activity a, Bundle b) {
                    if (isRunningActivity(a)) {
                        runningActivity = new WeakReference<Activity>(a);
                        finishTriggered = false;
                        if (!armed && persistedArmed(a)) {
                            armed = true;   // 进程重启后重建，仍要继续收尾
                            HfLog.i(TAG, "re-armed from persisted flag");
                        }
                        HfLog.i(TAG, "tracking run activity");
                    }
                }

                @Override public void onActivityStarted(Activity a) { }
                @Override public void onActivityResumed(Activity a) { }
                @Override public void onActivityPaused(Activity a) { }
                @Override public void onActivityStopped(Activity a) { }
                @Override public void onActivitySaveInstanceState(Activity a, Bundle b) { }

                @Override
                public void onActivityDestroyed(Activity a) {
                    Activity cur = runningActivity.get();
                    if (cur == a) runningActivity = new WeakReference<Activity>(null);
                }
            });
            HfLog.i(TAG, "activity tracker installed");
        } catch (Throwable t) {
            HfLog.e(TAG, "installActivityTracker err: " + t, t);
        }
    }

    private static boolean isRunningActivity(Activity a) {
        if (a == null) return false;
        String n = a.getClass().getName();
        return n.endsWith(".RangeRunningActivity")
                || n.endsWith(".FreeRunningActivity")
                || n.endsWith(".PointRunningActivity");
    }

    public static Activity currentRunningActivity() {
        return runningActivity.get();
    }

    /**
     * 读 App 自己算出的已跑距离（公里）。拿不到返回 -1。
     *
     * 真实调用点在 RunningActivity.O()：
     *   sget-object v1, LocationService;->a:LocationService$a;
     *   invoke-virtual {v1}, LocationService$a;->g()RunRealTimeInfo;
     *
     * 注意：jadx 把 LocationService$a 显示成 "LocationService.INSTANCE"，
     * 但 smali 里 LocationService 并没有 INSTANCE 字段，g() 也有两个同名方法
     * （LocationService.g()I 和 LocationService$a.g()RunRealTimeInfo）。
     * 这里按真实签名走，并保留 Activity→ViewModel 的备用路径。
     */
    public static double currentDistanceKm() {
        Object info = queryRunRealTimeInfo();
        if (info == null) return -1;
        try {
            Object d = info.getClass().getMethod("getGpsTotalDistance").invoke(info);
            if (d instanceof BigDecimal) return ((BigDecimal) d).doubleValue();
            if (d instanceof Number) return ((Number) d).doubleValue();
            return -1;
        } catch (Throwable t) {
            return -1;
        }
    }

    private static Object queryRunRealTimeInfo() {
        // 路径 1：LocationService.a.g()  —— 与 App 内部完全一致
        try {
            Class<?> ls = Class.forName(
                    "com.ledreamer.runningModule.service.LocationService");
            Object helper = ls.getField("a").get(null);
            if (helper != null) {
                Object info = helper.getClass().getMethod("g").invoke(helper);
                if (info != null) return info;
            }
        } catch (Throwable ignore) { }

        // 路径 2：Activity.v().m()
        try {
            Activity a = runningActivity.get();
            if (a != null) {
                Object vm = a.getClass().getMethod("v").invoke(a);
                if (vm != null) {
                    Object info = vm.getClass().getMethod("m").invoke(vm);
                    if (info != null) return info;
                }
            }
        } catch (Throwable ignore) { }
        return null;
    }

    /**
     * 每 tick 调用：跑到目标就把跑步页收尾。
     * @return true = 已触发收尾
     */
    public static boolean checkAndFinish(Context c) {
        return checkAndFinish(c, -1);
    }

    /**
     * @param fallbackKm 我方按配速算出的里程；App 读数拿不到时用它兜底，<0 表示不用
     */
    public static boolean checkAndFinish(Context c, double fallbackKm) {
        if (!armed || finishTriggered) return false;
        Activity a = runningActivity.get();
        if (a == null) return false;
        double km = currentDistanceKm();
        if (km < 0) {
            km = fallbackKm;
            if (km >= 0 && !fallbackWarned) {
                fallbackWarned = true;
                HfLog.w(TAG, "app distance unavailable, fallback to own estimate");
            }
        }
        float target = getTargetKm(c);
        if (km < 0 || km < target) return false;
        finishTriggered = true;
        HfLog.i(TAG, "target reached: " + km + " km >= " + target + " km, finishing");
        // 已经结束过（手动点了结束）就别再来一次，否则会重复上传
        try {
            Object over = a.getClass().getField("u").get(a);   // u = isOver
            if (Boolean.TRUE.equals(over)) {
                HfLog.i(TAG, "run already over, skip finish");
                armed = false;
                persistArmed(c, false);
                return false;
            }
        } catch (Throwable ignore) { }
        ensureAppUserInfo(c);              // 收尾前再确认一次，防止中途被清
        try {
            a.getClass().getMethod("S").invoke(a);   // public final void S()
            HfLog.i(TAG, "S() invoked");
            // 诊断：S() 之后 VO 有没有真的构建出来（null 就说明收尾链路被跳过）
            try {
                Object vo = a.getClass().getField("M").get(a);   // M = uploadRunInfoReqVo
                HfLog.i(TAG, "uploadVo = " + (vo == null ? "NULL(!)" : "built"));
                if (vo == null) {
                    HfLog.e(TAG, "上传数据没构建出来：检查 userInfo / serRuleCondition 是否缺失");
                }
            } catch (Throwable t) {
                HfLog.w(TAG, "读取 uploadRunInfoReqVo(M) 失败: " + t);
            }
            setLastRunDate(c, new java.text.SimpleDateFormat("yyyy-MM-dd",
                    java.util.Locale.US).format(new java.util.Date()));
            armed = false;
            persistArmed(c, false);
            return true;
        } catch (Throwable t) {
            HfLog.e(TAG, "invoke S() failed: " + t, t);
            finishTriggered = false;
            return false;
        }
    }

    /** 仅测试用：强制立即收尾。 */
    public static boolean forceFinishNow() {
        Activity a = runningActivity.get();
        if (a == null) return false;
        try {
            a.getClass().getMethod("S").invoke(a);
            return true;
        } catch (Throwable t) {
            HfLog.e(TAG, "forceFinishNow err: " + t, t);
            return false;
        }
    }
}
