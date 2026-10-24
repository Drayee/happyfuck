package com.ledreamer.hf;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.graphics.Typeface;
import android.view.ViewGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/**
 * 应用内日志查看器 —— 学生没有 adb 也能看到发生了什么。
 *
 * 从轨迹编辑器底部「日志」按钮进入。
 */
public class HfLogViewer {

    private static final int MAX_LINES = 800;

    public static void show(final Activity act) {
        if (act == null || act.isFinishing()) return;

        String text = HfLog.read(act, MAX_LINES);

        TextView tv = new TextView(act);
        tv.setTextSize(10f);
        tv.setTypeface(Typeface.MONOSPACE);
        tv.setTextIsSelectable(true);
        tv.setPadding(24, 16, 24, 16);
        tv.setText(text);

        ScrollView sv = new ScrollView(act);
        sv.addView(tv, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        new AlertDialog.Builder(act)
                .setTitle("运行日志")
                .setView(sv)
                .setPositiveButton("关闭", null)
                .setNeutralButton("清空", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        HfLog.clear(act);
                        Toast.makeText(act, "已清空", Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton("文件位置", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        showPaths(act);
                    }
                })
                .show();
    }

    public static void showPaths(final Activity act) {
        String sep = System.getProperty("line.separator");
        if (sep == null) sep = "\n";
        String msg = "应用内（卸载才清）：" + sep
                + HfLog.path(act) + sep + sep
                + "文件管理器可见：" + sep
                + HfLog.extPath(act);
        new AlertDialog.Builder(act)
                .setTitle("日志文件位置")
                .setMessage(msg)
                .setPositiveButton("好", null)
                .show();
    }
}
