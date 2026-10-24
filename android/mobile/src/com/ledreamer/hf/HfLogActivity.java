package com.ledreamer.hf;

import android.app.Activity;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/**
 * 独立日志页 —— 长按桌面图标 → 「运行日志」直接进。
 *
 * 不加载地图，打开很快，只做一件事：把 hf_log.txt 显示出来。
 */
public class HfLogActivity extends Activity {

    private TextView body;
    private ScrollView scroll;
    private TextView head;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        HfLog.init(this);
        setContentView(buildUi());
        refresh();
    }

    private View buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);

        head = new TextView(this);
        head.setTextSize(11f);
        head.setPadding(16, 10, 16, 10);
        head.setText("加载中…");
        root.addView(head, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        scroll = new ScrollView(this);
        body = new TextView(this);
        body.setTextSize(10f);
        body.setTypeface(Typeface.MONOSPACE);
        body.setTextIsSelectable(true);
        body.setPadding(16, 8, 16, 16);
        scroll.addView(body, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER);
        bar.addView(mkBtn("刷新", new View.OnClickListener() {
            @Override public void onClick(View v) { refresh(); }
        }));
        bar.addView(mkBtn("清空", new View.OnClickListener() {
            @Override public void onClick(View v) {
                HfLog.clear(HfLogActivity.this);
                refresh();
            }
        }));
        bar.addView(mkBtn("路径", new View.OnClickListener() {
            @Override public void onClick(View v) {
                HfLogViewer.showPaths(HfLogActivity.this);
            }
        }));
        bar.addView(mkBtn("关闭", new View.OnClickListener() {
            @Override public void onClick(View v) { finish(); }
        }));
        root.addView(bar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));

        return root;
    }

    private Button mkBtn(String text, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(13f);
        b.setOnClickListener(l);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        p.setMargins(4, 4, 4, 4);
        b.setLayoutParams(p);
        return b;
    }

    private void refresh() {
        try {
            String t = HfLog.read(this, 2000);
            if (t == null || t.trim().isEmpty()) {
                t = "（还没有日志）\n\n"
                        + "自动跑起来后这里会有内容。\n"
                        + "也可以先回编辑器点「立即试跑」触发一次。";
            }
            body.setText(t);
            head.setText("共 " + t.split("\n").length + " 行 · 最新在最后");
            scroll.post(new Runnable() {
                @Override public void run() {
                    scroll.fullScroll(View.FOCUS_DOWN);
                }
            });
        } catch (Throwable e) {
            body.setText("读取失败: " + e);
        }
    }
}
