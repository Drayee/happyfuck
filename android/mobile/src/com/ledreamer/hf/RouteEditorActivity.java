package com.ledreamer.hf;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.DialogInterface;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.amap.api.maps.AMap;
import com.amap.api.maps.CameraUpdateFactory;
import com.amap.api.maps.MapView;
import com.amap.api.maps.MapsInitializer;
import com.amap.api.maps.model.LatLng;
import com.amap.api.maps.model.Marker;
import com.amap.api.maps.model.MarkerOptions;
import com.amap.api.maps.model.Polygon;
import com.amap.api.maps.model.PolygonOptions;
import com.amap.api.maps.model.Polyline;
import com.amap.api.maps.model.PolylineOptions;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.List;

/**
 * 跑道编辑器 —— 在手机上手指点圈，保存后下次跑步直接用它。
 *
 * 入口：长按桌面图标 → 「设计跑步轨迹」（见 res/xml/hf_shortcuts.xml）
 *
 * 交互：
 *  - 地图上单击加点
 *  - 撤销 / 清空 / 保存
 *  - 红色虚线为学校围栏（服务端下发，跑步时自动存到 hf_fence.txt）
 *
 * 坐标系：高德返回 GCJ-02，与跑步引擎一致，不做转换。
 */
public class RouteEditorActivity extends Activity implements AMap.OnMapClickListener {

    private static final String TAG = "HF_EDIT";

    private MapView mapView;
    private AMap aMap;
    private TextView info;

    private final List<LatLng> pts = new ArrayList<LatLng>();
    private final List<Marker> marks = new ArrayList<Marker>();
    private Polyline line;
    private Polygon fencePoly;

    private double pace = 450.0;
    private double noise = 0.9;

    // =====================================================================
    // 生命周期
    // =====================================================================

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        HfLog.init(this);
        // 高德要求：用任何地图接口前先声明隐私合规，否则拒绝渲染（errorCode 555570）
        try {
            MapsInitializer.updatePrivacyShow(this, true, true);
            MapsInitializer.updatePrivacyAgree(this, true);
        } catch (Throwable ignore) { }
        try {
            setContentView(buildUi());
            mapView.onCreate(savedInstanceState);
            aMap = mapView.getMap();
            aMap.setOnMapClickListener(this);
            aMap.getUiSettings().setZoomControlsEnabled(true);
            aMap.getUiSettings().setScaleControlsEnabled(true);
            // 定位图层默认开启，会拉起定位并触发权限请求 —— 本编辑器不需要
            aMap.getUiSettings().setMyLocationButtonEnabled(false);

            loadFence();
            loadExistingRoute();
            moveCameraToFenceOrRoute();
            refreshInfo();
            HfLog.i(TAG, "editor opened, fence=" + (fencePoly != null)
                    + " existing=" + pts.size());
        } catch (Throwable t) {
            HfLog.e(TAG, "onCreate failed", t);
            Toast.makeText(this, "编辑器初始化失败: " + t, Toast.LENGTH_LONG).show();
            finish();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (mapView != null) mapView.onResume();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (mapView != null) mapView.onPause();
    }

    @Override
    protected void onDestroy() {
        if (mapView != null) mapView.onDestroy();
        super.onDestroy();
    }

    @Override
    public void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (mapView != null) mapView.onSaveInstanceState(outState);
    }

    // =====================================================================
    // UI
    // =====================================================================

    private View buildUi() {
        FrameLayout root = new FrameLayout(this);

        mapView = new MapView(this);
        root.addView(mapView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        info = new TextView(this);
        info.setTextColor(Color.WHITE);
        info.setBackgroundColor(0x99000000);
        info.setPadding(24, 16, 24, 16);
        info.setTextSize(13f);
        FrameLayout.LayoutParams ip = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        ip.gravity = Gravity.TOP;
        root.addView(info, ip);

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setBackgroundColor(0xCC000000);
        bar.setPadding(12, 12, 12, 12);

        bar.addView(makeBtn("撤销", new View.OnClickListener() {
            @Override
            public void onClick(View v) { undo(); }
        }));
        bar.addView(makeBtn("清空", new View.OnClickListener() {
            @Override
            public void onClick(View v) { clearAll(); }
        }));
        bar.addView(makeBtn("自动", new View.OnClickListener() {
            @Override
            public void onClick(View v) { openAutoSettings(); }
        }));
        bar.addView(makeBtn("保存", new View.OnClickListener() {
            @Override
            public void onClick(View v) { save(); }
        }));
        bar.addView(makeBtn("日志", new View.OnClickListener() {
            @Override
            public void onClick(View v) { HfLogViewer.show(RouteEditorActivity.this); }
        }));
        bar.addView(makeBtn("关闭", new View.OnClickListener() {
            @Override
            public void onClick(View v) { finish(); }
        }));

        FrameLayout.LayoutParams bp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        bp.gravity = Gravity.BOTTOM;
        root.addView(bar, bp);
        return root;
    }

    private Button makeBtn(String text, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(12f);
        b.setOnClickListener(l);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        p.setMargins(2, 0, 2, 0);
        b.setLayoutParams(p);
        return b;
    }

    // =====================================================================
    // 地图交互
    // =====================================================================

    @Override
    public void onMapClick(LatLng latLng) {
        if (latLng == null) return;
        pts.add(latLng);
        MarkerOptions mo = new MarkerOptions()
                .position(latLng)
                .title(String.valueOf(pts.size()));
        Marker m = aMap.addMarker(mo);
        if (m != null) marks.add(m);
        redraw();
        refreshInfo();
    }

    private void undo() {
        if (pts.isEmpty()) return;
        pts.remove(pts.size() - 1);
        if (!marks.isEmpty()) {
            Marker m = marks.remove(marks.size() - 1);
            if (m != null) m.remove();
        }
        redraw();
        refreshInfo();
    }

    private void clearAll() {
        pts.clear();
        for (Marker m : marks) {
            if (m != null) m.remove();
        }
        marks.clear();
        if (line != null) {
            line.remove();
            line = null;
        }
        refreshInfo();
    }

    private void redraw() {
        if (line != null) {
            line.remove();
            line = null;
        }
        if (pts.size() < 2) return;
        PolylineOptions po = new PolylineOptions()
                .addAll(new ArrayList<LatLng>(pts))
                .color(0xFF1E88E5)
                .width(10f);
        if (pts.size() >= 3) {
            po.add(pts.get(0));   // 闭合显示
        }
        line = aMap.addPolyline(po);
    }

    private void refreshInfo() {
        double len = loopLenM(pts);
        StringBuilder sb = new StringBuilder();
        sb.append("顶点 ").append(pts.size()).append("  |  周长 ")
          .append(Math.round(len)).append(" m");
        if (len > 10) {
            int sec = (int) Math.round(len / 1000.0 * pace);
            sb.append("  |  跑完约 ").append(fmt(sec));
        }
        sb.append('\n');
        if (fencePoly == null) {
            sb.append("还没拿到学校围栏：先跑一次范围跑，编辑器会自动定位到学校");
        } else {
            sb.append("红色虚线 = 学校围栏，请在它内部点圈；点「保存」生效");
        }
        info.setText(sb.toString());
    }

    // =====================================================================
    // 围栏
    // =====================================================================

    /** 优先读本地缓存的围栏；没有就尝试从正在运行的 LocationService 抓一次。 */
    private void loadFence() {
        List<LatLng> fence = readPoints(new File(getFilesDir(), "hf_fence.txt"));
        if (fence.size() < 3) {
            fence = tryGrabFenceFromService();
        }
        if (fence.size() < 3) {
            HfLog.i(TAG, "no fence available");
            return;
        }
        PolygonOptions po = new PolygonOptions();
        for (LatLng p : fence) po.add(p);
        po.strokeColor(0xFFFF1744).strokeWidth(6f)
          .fillColor(0x22FF1744);
        fencePoly = aMap.addPolygon(po);
        HfLog.i(TAG, "fence drawn, points=" + fence.size());
    }

    private List<LatLng> tryGrabFenceFromService() {
        try {
            Class<?> ls = Class.forName(
                    "com.ledreamer.runningModule.service.LocationService");
            Object poly = ls.getField("h").get(null);
            if (poly == null) return new ArrayList<LatLng>();
            List<?> list = (List<?>) poly.getClass().getMethod("getPoints").invoke(poly);
            List<LatLng> out = new ArrayList<LatLng>();
            if (list != null) {
                for (Object o : list) {
                    if (o instanceof LatLng) out.add((LatLng) o);
                }
            }
            if (out.size() >= 3) {
                saveFence(out);   // 顺手缓存，下次就不用再抓
                HfLog.i(TAG, "fence grabbed from service: " + out.size());
            }
            return out;
        } catch (Throwable t) {
            HfLog.i(TAG, "grab fence failed: " + t);
            return new ArrayList<LatLng>();
        }
    }

    private void saveFence(List<LatLng> fence) {
        try {
            File f = new File(getFilesDir(), "hf_fence.txt");
            FileWriter w = new FileWriter(f, false);
            for (LatLng p : fence) {
                w.write(p.latitude + "," + p.longitude + "\n");
            }
            w.close();
        } catch (Throwable t) {
            HfLog.e(TAG, "saveFence err: " + t);
        }
    }

    // =====================================================================
    // 已有轨迹
    // =====================================================================

    private void loadExistingRoute() {
        File f = new File(getFilesDir(), "hf_route.txt");
        String text = null;
        if (f.exists()) {
            text = readText(f);
        } else {
            File extDir = getExternalFilesDir(null);
            if (extDir != null) {
                File ext = new File(extDir, "hf_route.txt");
                if (ext.exists()) text = readText(ext);
            }
        }
        if (text == null) return;
        for (String ln : text.split("\n")) {
            ln = ln.trim();
            if (ln.isEmpty() || ln.startsWith("#")) continue;
            int eq = ln.indexOf('=');
            if (eq > 0) {
                String k = ln.substring(0, eq).trim().toLowerCase();
                String v = ln.substring(eq + 1).trim();
                try {
                    if (k.equals("pace")) pace = Double.parseDouble(v);
                    else if (k.equals("noise")) noise = Double.parseDouble(v);
                } catch (Exception ignore) { }
                continue;
            }
            String[] p = ln.split(",");
            if (p.length >= 2) {
                try {
                    double la = Double.parseDouble(p[0].trim());
                    double lo = Double.parseDouble(p[1].trim());
                    pts.add(new LatLng(la, lo));
                } catch (Exception ignore) { }
            }
        }
        for (LatLng p : pts) {
            MarkerOptions mo = new MarkerOptions().position(p);
            Marker m = aMap.addMarker(mo);
            if (m != null) marks.add(m);
        }
        redraw();
        HfLog.i(TAG, "existing route loaded: " + pts.size());
    }

    // =====================================================================
    // 每日自动跑设置
    // =====================================================================

    private void openAutoSettings() {
        final Context ctx = this;

        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(48, 32, 48, 16);

        final CheckBox cbEnable = new CheckBox(this);
        cbEnable.setText("启用每日自动跑");
        cbEnable.setChecked(HfAutoRun.isEnabled(this));
        box.addView(cbEnable);

        TextView modeTitle = new TextView(this);
        modeTitle.setText("模式");
        modeTitle.setPadding(0, 20, 0, 4);
        box.addView(modeTitle);

        final RadioGroup rg = new RadioGroup(this);
        final RadioButton rbSemi = new RadioButton(this);
        rbSemi.setText("半自动：到点发通知，点一下开跑");
        rbSemi.setId(0x7f0f0001);
        final RadioButton rbAuto = new RadioButton(this);
        rbAuto.setText("全自动：到点直接开跑（需悬浮窗权限）");
        rbAuto.setId(0x7f0f0002);
        rg.addView(rbSemi);
        rg.addView(rbAuto);
        rg.check(HfAutoRun.MODE_AUTO.equals(HfAutoRun.getMode(this))
                ? rbAuto.getId() : rbSemi.getId());
        box.addView(rg);

        TextView timeTitle = new TextView(this);
        timeTitle.setText("每天触发时间");
        timeTitle.setPadding(0, 20, 0, 4);
        box.addView(timeTitle);

        LinearLayout timeRow = new LinearLayout(this);
        timeRow.setOrientation(LinearLayout.HORIZONTAL);
        final EditText etHour = new EditText(this);
        etHour.setInputType(InputType.TYPE_CLASS_NUMBER);
        etHour.setText(String.valueOf(HfAutoRun.getHour(this)));
        etHour.setWidth(160);
        TextView colon = new TextView(this);
        colon.setText(" : ");
        colon.setTextSize(18f);
        final EditText etMin = new EditText(this);
        etMin.setInputType(InputType.TYPE_CLASS_NUMBER);
        etMin.setText(String.format("%02d", HfAutoRun.getMinute(this)));
        etMin.setWidth(160);
        timeRow.addView(etHour);
        timeRow.addView(colon);
        timeRow.addView(etMin);
        box.addView(timeRow);

        TextView targetTitle = new TextView(this);
        targetTitle.setText("目标距离（公里）");
        targetTitle.setPadding(0, 20, 0, 4);
        box.addView(targetTitle);

        final EditText etTarget = new EditText(this);
        etTarget.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        etTarget.setText(String.valueOf(HfAutoRun.getTargetKm(this)));
        box.addView(etTarget);

        TextView hint = new TextView(this);
        hint.setTextSize(12f);
        hint.setPadding(0, 20, 0, 0);
        hint.setText("说明：先把轨迹画好并保存；第一次请手动跑一次，"
                + "App 会记住本次参数，之后每天才能自动跑。\n"
                + "日志过滤 HF_AUTO / HF_ALARM / HF_SCHED 可看执行情况。");
        box.addView(hint);

        new AlertDialog.Builder(this)
                .setTitle("每日自动跑")
                .setView(box)
                .setPositiveButton("保存", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        int h = parseInt(etHour.getText().toString(), 6);
                        int m = parseInt(etMin.getText().toString(), 30);
                        float km = parseFloat(etTarget.getText().toString(),
                                HfAutoRun.DEFAULT_TARGET_KM);
                        if (h < 0 || h > 23) h = 6;
                        if (m < 0 || m > 59) m = 30;
                        if (km < 0.5f) km = 0.5f;

                        HfAutoRun.setEnabled(ctx, cbEnable.isChecked());
                        HfAutoRun.setTime(ctx, h, m);
                        HfAutoRun.setTargetKm(ctx, km);
                        HfAutoRun.setMode(ctx,
                                rg.getCheckedRadioButtonId() == rbAuto.getId()
                                        ? HfAutoRun.MODE_AUTO : HfAutoRun.MODE_NOTIFY);

                        HfScheduler.schedule(ctx);
                        Toast.makeText(ctx, HfAutoRun.isEnabled(ctx)
                                ? String.format("已开启：每天 %02d:%02d · %s · %.1fkm",
                                    h, m,
                                    HfAutoRun.MODE_AUTO.equals(HfAutoRun.getMode(ctx))
                                            ? "全自动" : "半自动", km)
                                : "已关闭每日自动跑",
                                Toast.LENGTH_LONG).show();
                    }
                })
                .setNeutralButton("立即试跑", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        if (!HfAutoRun.hasCapturedExtras(ctx)) {
                            Toast.makeText(ctx,
                                    "还没有基准参数：请先手动跑一次范围跑",
                                    Toast.LENGTH_LONG).show();
                            return;
                        }
                        boolean ok = HfAutoRun.startRun(ctx);
                        Toast.makeText(ctx, ok ? "已启动，跑到目标距离会自动结束上传"
                                        : "启动失败，检查后台弹出/悬浮窗权限",
                                Toast.LENGTH_LONG).show();
                        if (ok) finish();
                    }
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private static int parseInt(String s, int def) {
        try {
            return Integer.parseInt(s.trim());
        } catch (Exception e) {
            return def;
        }
    }

    private static float parseFloat(String s, float def) {
        try {
            return Float.parseFloat(s.trim());
        } catch (Exception e) {
            return def;
        }
    }

    // =====================================================================
    // 保存
    // =====================================================================

    private void save() {
        if (pts.size() < 3) {
            Toast.makeText(this, "至少点 3 个顶点", Toast.LENGTH_SHORT).show();
            return;
        }
        double len = loopLenM(pts);
        if (len < 50) {
            Toast.makeText(this, "跑道太短（" + Math.round(len) + " m）",
                    Toast.LENGTH_SHORT).show();
            return;
        }
        StringBuilder sb = new StringBuilder();
        sb.append("# HappyFuck route (drawn in app)\n");
        sb.append("pace=").append((int) pace).append('\n');
        sb.append("noise=").append(noise).append('\n');
        sb.append("cadence=172\n");
        for (LatLng p : pts) {
            sb.append(p.latitude).append(',').append(p.longitude).append('\n');
        }
        String content = sb.toString();

        boolean ok = writeFile(new File(getFilesDir(), "hf_route.txt"), content);
        File extDir = getExternalFilesDir(null);
        if (extDir != null) {
            writeFile(new File(extDir, "hf_route.txt"), content);
        }
        if (!ok) {
            Toast.makeText(this, "保存失败", Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            SyntheticGps.load(this);   // 立即热加载
        } catch (Throwable ignore) { }
        HfLog.i(TAG, "route saved: " + pts.size() + " pts, " + Math.round(len) + " m");
        Toast.makeText(this, "已保存 " + pts.size() + " 点 / "
                + Math.round(len) + " m", Toast.LENGTH_LONG).show();
        finish();
    }

    private boolean writeFile(File f, String content) {
        try {
            FileWriter w = new FileWriter(f, false);
            w.write(content);
            w.close();
            return true;
        } catch (Throwable t) {
            HfLog.e(TAG, "write " + f + " err: " + t);
            return false;
        }
    }

    // =====================================================================
    // 工具
    // =====================================================================

    private void moveCameraToFenceOrRoute() {
        LatLng center = null;
        if (!pts.isEmpty()) {
            center = pts.get(0);
        } else if (fencePoly != null) {
            List<LatLng> fp = fencePoly.getPoints();
            if (fp != null && !fp.isEmpty()) center = fp.get(0);
        }
        if (center == null) {
            List<LatLng> cached = readPoints(new File(getFilesDir(), "hf_fence.txt"));
            if (!cached.isEmpty()) center = cached.get(0);
        }
        if (center != null) {
            aMap.moveCamera(CameraUpdateFactory.newLatLngZoom(center, 16f));
        }
    }

    private static double loopLenM(List<LatLng> p) {
        int n = p.size();
        if (n < 2) return 0;
        double s = 0;
        for (int i = 0; i < n; i++) {
            LatLng a = p.get(i);
            LatLng b = p.get((i + 1) % n);
            s += hav(a.latitude, a.longitude, b.latitude, b.longitude);
        }
        return s;
    }

    private static double hav(double la1, double lo1, double la2, double lo2) {
        double R = 6371000.0;
        double dLa = Math.toRadians(la2 - la1);
        double dLo = Math.toRadians(lo2 - lo1);
        double a = Math.sin(dLa / 2) * Math.sin(dLa / 2)
                 + Math.cos(Math.toRadians(la1)) * Math.cos(Math.toRadians(la2))
                   * Math.sin(dLo / 2) * Math.sin(dLo / 2);
        return 2 * R * Math.asin(Math.min(1.0, Math.sqrt(a)));
    }

    private static String fmt(int sec) {
        int h = sec / 3600;
        int m = (sec % 3600) / 60;
        if (h > 0) return h + "h" + m + "m";
        return m + "min";
    }

    private static String readText(File f) {
        try {
            StringBuilder sb = new StringBuilder();
            BufferedReader r = new BufferedReader(new FileReader(f));
            String ln;
            while ((ln = r.readLine()) != null) sb.append(ln).append('\n');
            r.close();
            return sb.toString();
        } catch (Throwable t) {
            return null;
        }
    }

    private static List<LatLng> readPoints(File f) {
        List<LatLng> out = new ArrayList<LatLng>();
        String text = readText(f);
        if (text == null) return out;
        for (String ln : text.split("\n")) {
            ln = ln.trim();
            if (ln.isEmpty() || ln.startsWith("#") || ln.indexOf('=') > 0) continue;
            String[] p = ln.split(",");
            if (p.length >= 2) {
                try {
                    out.add(new LatLng(Double.parseDouble(p[0].trim()),
                            Double.parseDouble(p[1].trim())));
                } catch (Exception ignore) { }
            }
        }
        return out;
    }
}
