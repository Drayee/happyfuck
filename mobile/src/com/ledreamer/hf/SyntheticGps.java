package com.ledreamer.hf;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import com.amap.api.location.AMapLocation;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileWriter;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * HappyFuck 手机版 —— 合成 GPS 注入器。
 *
 * 两种轨迹模式（自动选择）：
 *
 *  A. 关键点模式（推荐）：读 hf_route.txt —— 稀疏闭合折线（画圈得到的拐点/关键点），
 *     运行时按「配速 × 已用时间」沿折线插值，再叠加随机 GPS 噪声。
 *     => 每次跑出来的坐标都不同，不是逐字节重复的固定点表。
 *
 *  B. 固定点模式（兼容旧资产）：读 hf_track.txt —— 每行 lat,lon,speed，按 cursor 逐点取。
 *
 * 文件查找顺序（两种模式都是）：
 *   1) 外部：/sdcard/Android/data/com.ledreamer.zz/files/hf_route.txt
 *      -> 换圈不用重新签 APK，adb push 即可
 *   2) 内置：assets/hf_route.txt（或 hf_track.txt）
 *
 * 注入方式：定时器每秒反射调用 LocationService.onLocationChanged(AMapLocation)，
 * 完全复用 App 自身的距离/配速/围栏/打卡点/上传逻辑。
 */
public class SyntheticGps {

    // ---- 模式 B：固定点 ----
    public static boolean enabled = false;
    public static int cursor = 0;
    public static int count = 0;
    public static List<String> lat = new ArrayList<>();
    public static List<String> lon = new ArrayList<>();
    public static List<String> speed = new ArrayList<>();

    // ---- 模式 A：关键点 ----
    private static double[] wpLat = null;
    private static double[] wpLon = null;
    private static double[] segLen = null;   // 每段长度（含闭合段）
    private static double totalLen = 0.0;
    private static boolean routeMode = false;

    // ---- 可调参数 ----
    private static double paceSPerKm = 450.0;   // 秒/公里
    private static double noiseM = 0.9;         // GPS 噪声标准差（米）
    private static double cadencePerMin = 172.0; // 步/分钟
    /** AR(1) 系数：越大噪声越平滑、里程越准 */
    private static final double AR = 0.95;
    /** AR(1) 噪声状态（米） */
    private static double nLatM = 0, nLonM = 0;
    /** tick 计数：用于前几拍抓围栏 */
    private static int tickN = 0;

    // ---- 运行时 ----
    private static Handler driver = null;
    private static Method onLocMethod = null;
    private static Field runTypeField = null;
    private static boolean driverOn = false;
    private static long startTs = 0L;
    private static final Random RND = new Random();
    private static double lastLat = 0, lastLon = 0;
    private static boolean TEST_ALL_RUN_TYPES = false;

    // =====================================================================
    // 加载
    // =====================================================================

    public static void load(Context ctx) {
        HfLog.init(ctx);
        HfLog.i("HF_LOAD", "start");
        try {
            HfAutoRun.installActivityTracker(ctx);
            HfScheduler.ensureChannel(ctx);
        } catch (Throwable ignore) { }
        reset();
        try {
            // 1) 外部关键点文件优先
            File ext = externalFile(ctx, "hf_route.txt");
            if (ext != null && ext.exists() && ext.length() > 0) {
                HfLog.i("HF_LOAD", "using external " + ext.getAbsolutePath());
                parseRoute(new FileInputStream(ext));
                if (routeMode) {
                    enabled = true;
                    HfLog.i("HF_LOAD", "route mode: waypoints=" + wpLat.length
                            + " totalLen=" + Math.round(totalLen) + "m"
                            + " pace=" + paceSPerKm + "s/km noise=" + noiseM + "m");
                    probeRengis(ctx);
                    return;
                }
            }
            // 2) 内部存储（App 内画圈保存的位置，最常用）
            File inner = new File(ctx.getFilesDir(), "hf_route.txt");
            if (inner.exists() && inner.length() > 0) {
                HfLog.i("HF_LOAD", "using internal " + inner.getAbsolutePath());
                parseRoute(new FileInputStream(inner));
                if (routeMode) {
                    enabled = true;
                    HfLog.i("HF_LOAD", "route mode(internal): waypoints=" + wpLat.length
                            + " totalLen=" + Math.round(totalLen) + "m");
                    probeRengis(ctx);
                    return;
                }
            }
            // 3) 内置关键点
            try {
                parseRoute(ctx.getAssets().open("hf_route.txt"));
                if (routeMode) {
                    enabled = true;
                    HfLog.i("HF_LOAD", "asset route mode: waypoints=" + wpLat.length
                            + " totalLen=" + Math.round(totalLen) + "m");
                    probeRengis(ctx);
                    return;
                }
            } catch (Exception ignore) {
                HfLog.i("HF_LOAD", "no assets/hf_route.txt, fallback to hf_track.txt");
            }
            // 3) 外部固定点表
            File ext2 = externalFile(ctx, "hf_track.txt");
            if (ext2 != null && ext2.exists() && ext2.length() > 0) {
                HfLog.i("HF_LOAD", "using external " + ext2.getAbsolutePath());
                parseTrack(new FileInputStream(ext2));
            } else {
                parseTrack(ctx.getAssets().open("hf_track.txt"));
            }
            enabled = count > 0;
            HfLog.i("HF_LOAD", "track mode: points=" + count);
            probeRengis(ctx);
        } catch (Exception e) {
            HfLog.e("HF_LOAD", "error: " + e.getMessage(), e);
        }
    }

    private static void reset() {
        lat.clear();
        lon.clear();
        speed.clear();
        cursor = 0;
        count = 0;
        wpLat = null;
        wpLon = null;
        segLen = null;
        totalLen = 0;
        routeMode = false;
        enabled = false;
        paceSPerKm = 450.0;
        noiseM = 3.0;
        cadencePerMin = 172.0;
    }

    private static File externalFile(Context ctx, String name) {
        try {
            File dir = ctx.getExternalFilesDir(null);
            return dir == null ? null : new File(dir, name);
        } catch (Throwable t) {
            return null;
        }
    }

    /**
     * 解析关键点文件。格式：
     *   # 注释
     *   pace=450        秒/公里
     *   noise=3.0       噪声半径（米）
     *   cadence=172     步/分钟
     *   lat,lon         关键点（闭环，>=3 个）
     */
    private static void parseRoute(InputStream is) throws Exception {
        List<double[]> pts = new ArrayList<double[]>();
        BufferedReader r = new BufferedReader(new InputStreamReader(is, "UTF-8"));
        String line;
        while ((line = r.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            int eq = line.indexOf('=');
            if (eq > 0) {
                String k = line.substring(0, eq).trim().toLowerCase();
                String v = line.substring(eq + 1).trim();
                try {
                    if (k.equals("pace")) paceSPerKm = Double.parseDouble(v);
                    else if (k.equals("noise")) noiseM = Double.parseDouble(v);
                    else if (k.equals("cadence")) cadencePerMin = Double.parseDouble(v);
                } catch (Exception ignore) { }
                continue;
            }
            String[] p = line.split(",");
            if (p.length >= 2) {
                try {
                    pts.add(new double[]{Double.parseDouble(p[0].trim()),
                                         Double.parseDouble(p[1].trim())});
                } catch (Exception ignore) { }
            }
        }
        r.close();
        if (pts.size() < 3) {
            HfLog.w("HF_LOAD", "waypoints too few: " + pts.size());
            return;
        }
        int n = pts.size();
        wpLat = new double[n];
        wpLon = new double[n];
        for (int i = 0; i < n; i++) {
            wpLat[i] = pts.get(i)[0];
            wpLon[i] = pts.get(i)[1];
        }
        segLen = new double[n];
        totalLen = 0;
        for (int i = 0; i < n; i++) {
            int j = (i + 1) % n;
            segLen[i] = hav(wpLat[i], wpLon[i], wpLat[j], wpLon[j]);
            totalLen += segLen[i];
        }
        routeMode = totalLen > 10.0;
        if (paceSPerKm <= 0) paceSPerKm = 450.0;
        if (noiseM < 0) noiseM = 0;
        if (cadencePerMin <= 0) cadencePerMin = 172.0;
    }

    /** 兼容旧的固定点表：lat,lon,speed */
    private static void parseTrack(InputStream is) throws Exception {
        BufferedReader r = new BufferedReader(new InputStreamReader(is, "UTF-8"));
        String line;
        while ((line = r.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] p = line.split(",");
            if (p.length >= 3) {
                lat.add(p[0]);
                lon.add(p[1]);
                speed.add(p[2]);
            }
        }
        r.close();
        count = lat.size();
        cursor = 0;
    }

    // =====================================================================
    // 几何
    // =====================================================================

    private static double hav(double la1, double lo1, double la2, double lo2) {
        double R = 6371000.0;
        double dLa = Math.toRadians(la2 - la1);
        double dLo = Math.toRadians(lo2 - lo1);
        double a = Math.sin(dLa / 2) * Math.sin(dLa / 2)
                 + Math.cos(Math.toRadians(la1)) * Math.cos(Math.toRadians(la2))
                   * Math.sin(dLo / 2) * Math.sin(dLo / 2);
        return 2 * R * Math.asin(Math.min(1.0, Math.sqrt(a)));
    }

    /** 沿闭合折线走 d 米，返回 {lat, lon}。 */
    private static double[] pointAt(double d) {
        int n = wpLat.length;
        if (totalLen <= 0) return new double[]{wpLat[0], wpLon[0]};
        d = d % totalLen;
        if (d < 0) d += totalLen;
        for (int i = 0; i < n; i++) {
            if (d <= segLen[i]) {
                double f = segLen[i] > 0 ? d / segLen[i] : 0;
                int j = (i + 1) % n;
                return new double[]{
                        wpLat[i] + (wpLat[j] - wpLat[i]) * f,
                        wpLon[i] + (wpLon[j] - wpLon[i]) * f};
            }
            d -= segLen[i];
        }
        return new double[]{wpLat[0], wpLon[0]};
    }

    // =====================================================================
    // 注入
    // =====================================================================

    public static void inject(AMapLocation loc) {
        if (!enabled) return;
        try {
            if (routeMode) {
                injectRoute(loc);
            } else {
                injectTrack(loc);
            }
        } catch (Throwable t) {
            HfLog.e("HF_INJ", "error: " + t);
        }
    }

    /** 关键点模式：按时间推进 + 随机噪声。 */
    private static void injectRoute(AMapLocation loc) {
        double elapsed = (System.currentTimeMillis() - startTs) / 1000.0;
        if (elapsed < 0) elapsed = 0;
        double mps = 1000.0 / paceSPerKm;          // 米/秒
        double d = mps * elapsed;
        double[] base = pointAt(d);

        // AR(1) 时间相关噪声：绝对偏移保持 ~noiseM 标准差（贴近真实 GPS 精度），
        // 但逐 tick 的变化很小，不会虚增里程。
        // （独立噪声会让 3.5km 跑成 5km+，导致上报配速比设定快 15%，可能触发规则校验）
        double lat = base[0], lon = base[1];
        if (noiseM > 0) {
            double k = Math.sqrt(1 - AR * AR);
            nLatM = AR * nLatM + k * noiseM * RND.nextGaussian();
            nLonM = AR * nLonM + k * noiseM * RND.nextGaussian();
            double cosLat = Math.cos(Math.toRadians(base[0]));
            if (Math.abs(cosLat) < 1e-9) cosLat = 1e-9;
            lat += nLatM / 111320.0;
            lon += nLonM / (111320.0 * cosLat);
        }

        loc.setLatitude(lat);
        loc.setLongitude(lon);
        loc.setSpeed((float) mps);
        loc.setErrorCode(0);
        loc.setProvider("HF");
        loc.setAccuracy(5f);
        loc.setTime(System.currentTimeMillis());

        lastLat = lat;
        lastLon = lon;
        if (((int) elapsed) % 10 == 0) {
            HfLog.i("HF_INJ", "t=" + (int) elapsed + "s d=" + Math.round(d)
                    + "m lat=" + String.format("%.7f", lat)
                    + " lon=" + String.format("%.7f", lon));
        }
    }

    /** 固定点模式：保持旧行为。 */
    private static void injectTrack(AMapLocation loc) {
        if (count <= 0) return;
        if (cursor >= count) cursor = 0;
        double la = Double.parseDouble(lat.get(cursor));
        double lo = Double.parseDouble(lon.get(cursor));
        float sp = Float.parseFloat(speed.get(cursor));
        loc.setLatitude(la);
        loc.setLongitude(lo);
        loc.setSpeed(sp);
        loc.setErrorCode(0);
        loc.setProvider("HF");
        loc.setAccuracy(5f);
        loc.setTime(System.currentTimeMillis());
        lastLat = la;
        lastLon = lo;
        cursor++;
    }

    // =====================================================================
    // DCloud uni.getLocation 回调（绕过 AMap）
    // =====================================================================

    public static String geoJson() {
        double la = lastLat, lo = lastLon;
        if (la == 0 && lo == 0) {
            if (routeMode) {
                la = wpLat[0];
                lo = wpLon[0];
            } else if (count > 0) {
                la = Double.parseDouble(lat.get(0));
                lo = Double.parseDouble(lon.get(0));
            } else {
                la = 29.9821616;
                lo = 102.986433;
            }
        }
        return "{\"latitude\":" + la + ",\"longitude\":" + lo
                + ",\"altitude\":0,\"accuracy\":5,\"altitudeAccuracy\":0"
                + ",\"heading\":0,\"velocity\":2.222"
                + ",\"coordsType\":\"gcj02\",\"timestamp\":"
                + System.currentTimeMillis() + "}";
    }

    public static void forceGeoCallback(Object webview, String cbId) {
        try {
            Class<?> iw = Class.forName("io.dcloud.common.DHInterface.IWebview");
            Class<?> js = Class.forName("io.dcloud.common.util.JSUtil");
            Method m = js.getMethod("execGEOCallback", iw, String.class, String.class,
                    int.class, boolean.class, boolean.class);
            int ok = js.getField("OK").getInt(null);
            m.invoke(null, webview, cbId, geoJson(), ok, true, false);
            HfLog.i("HF_GEO", "callback sent ok=" + ok);
        } catch (Throwable t) {
            HfLog.e("HF_GEO", "callback err: " + t, t);
        }
    }

    // =====================================================================
    // 诊断
    // =====================================================================

    public static void probeRengis(Context ctx) {
        try {
            Class<?> rc = Class.forName("cn.legym.ai.util.Rengis");
            Object r = rc.getMethod("it", Context.class).invoke(null, ctx);
            HfLog.i("HF_RENGIS", "it=" + r);
            Object h = rc.getMethod("hs", String.class).invoke(null, "test");
            HfLog.i("HF_RENGIS", "hs(test)=" + h);
        } catch (Throwable t) {
            HfLog.e("HF_RENGIS", "err: " + t);
        }
    }

    // =====================================================================
    // 驱动
    // =====================================================================

    public static void startDriver(Context ctx) {
        if (driverOn) {
            HfLog.i("HF_DRV", "already running");
            return;
        }
        if (!enabled) {
            HfLog.i("HF_DRV", "disabled, skip");
            return;
        }
        try {
            onLocMethod = ctx.getClass().getMethod("onLocationChanged", AMapLocation.class);
            try {
                runTypeField = ctx.getClass().getField("w");
            } catch (Throwable ignore) {
                runTypeField = null;
            }
            driver = new Handler(Looper.getMainLooper());
            driverOn = true;
            startTs = System.currentTimeMillis();
            nLatM = 0;
            nLonM = 0;
            HfLog.i("HF_DRV", "start, class=" + ctx.getClass().getName()
                    + " routeMode=" + routeMode);
            driver.postDelayed(new Tick(ctx), 1000L);
        } catch (Throwable t) {
            HfLog.e("HF_DRV", "start failed", t);
        }
    }

    public static void stopDriver() {
        driverOn = false;
        if (driver != null) {
            driver.removeCallbacksAndMessages(null);
            driver = null;
        }
        HfLog.i("HF_DRV", "stopped");
    }

    /**
     * 把 LocationService 里服务端下发的围栏多边形存到 hf_fence.txt，
     * 供轨迹编辑器显示边界。已存过就跳过。
     */
    private static void saveFenceFromService(Context ctx) {
        try {
            File f = new File(ctx.getFilesDir(), "hf_fence.txt");
            if (f.exists() && f.length() > 0) return;
            Class<?> ls = Class.forName(
                    "com.ledreamer.runningModule.service.LocationService");
            Object poly = ls.getField("h").get(null);
            if (poly == null) return;
            List<?> list = (List<?>) poly.getClass().getMethod("getPoints").invoke(poly);
            if (list == null || list.size() < 3) return;
            StringBuilder sb = new StringBuilder();
            for (Object o : list) {
                Class<?> lc = o.getClass();
                double la = lc.getField("latitude").getDouble(o);
                double lo = lc.getField("longitude").getDouble(o);
                sb.append(la).append(',').append(lo).append('\n');
            }
            FileWriter w = new FileWriter(f, false);
            w.write(sb.toString());
            w.close();
            HfLog.i("HF_FENCE", "saved " + list.size() + " points -> " + f.getName());
        } catch (Throwable t) {
            HfLog.i("HF_FENCE", "skip: " + t);
        }
    }

    /** 合成步数：写 f.l.a.g.a.d 并触发回调。 */
    private static void syncSteps(Context ctx, long steps) {
        try {
            Field xf = ctx.getClass().getField("x");
            Object helper = xf.get(ctx);
            if (helper == null) return;
            BigDecimal val = new BigDecimal(steps);
            helper.getClass().getField("d").set(helper, val);
            try {
                Object cb = helper.getClass().getField("e").get(helper);
                if (cb != null) {
                    cb.getClass().getMethod("a", BigDecimal.class).invoke(cb, val);
                }
            } catch (Throwable ignore) { }
        } catch (Throwable t) {
            HfLog.e("HF_STEP", "err: " + t);
        }
    }

    private static class Tick implements Runnable {
        private final Context ctx;

        Tick(Context c) {
            this.ctx = c;
        }

        @Override
        public void run() {
            if (!driverOn || ctx == null) return;
            try {
                int runType = -1;
                if (runTypeField != null) {
                    try {
                        runType = runTypeField.getInt(ctx);
                    } catch (Throwable ignore) { }
                }
                // 0=自由跑 1=范围跑 2=定点跑；只排除定点跑
                boolean allow = TEST_ALL_RUN_TYPES || runType == -1
                        || runType == 0 || runType == 1;
                if (allow) {
                    // 前几拍顺手把服务端下发的围栏存下来，供轨迹编辑器显示
                    if (tickN < 3) saveFenceFromService(ctx);
                    tickN++;
                    // 自动跑：跑到目标距离就调 RunningActivity.S() 收尾上传
                    // 第二个参数是我方按配速估算的里程，仅在 App 读数拿不到时兜底
                    long el = (System.currentTimeMillis() - startTs) / 1000L;
                    double estKm = (paceSPerKm > 0 ? el / paceSPerKm : 0) * 1.02;
                    HfAutoRun.checkAndFinish(ctx, estKm);
                    long steps = Math.round(el * cadencePerMin / 60.0);
                    syncSteps(ctx, steps);

                    AMapLocation loc = new AMapLocation("HF");
                    loc.setErrorCode(0);
                    loc.setProvider("HF");
                    loc.setAccuracy(5f);
                    loc.setTime(System.currentTimeMillis());
                    onLocMethod.invoke(ctx, loc);
                }
            } catch (Throwable t) {
                HfLog.e("HF_DRV", "tick err: " + t);
            }
            if (driverOn && driver != null) {
                driver.postDelayed(this, 1000L);
            }
        }
    }
}
