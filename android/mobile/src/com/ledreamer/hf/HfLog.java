package com.ledreamer.hf;

import android.content.Context;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * 双写日志：logcat + 应用目录下的 hf_log.txt。
 *
 * 目的：学生没有 adb，也要能在手机上看到发生了什么。
 *
 * 落盘位置（两处都写）：
 *   1) <filesDir>/hf_log.txt
 *   2) <externalFilesDir>/hf_log.txt
 *      = /sdcard/Android/data/com.ledreamer.zz/files/hf_log.txt
 *
 * 查看：轨迹编辑器底部「日志」按钮（应用内直接看，无需 adb）
 */
public class HfLog {

    private static final String FILE = "hf_log.txt";
    private static final long MAX_BYTES = 512 * 1024;   // 超过就截断重来
    private static final Object LOCK = new Object();
    private static final SimpleDateFormat TS =
            new SimpleDateFormat("MM-dd HH:mm:ss.SSS", Locale.US);

    private static Context appCtx = null;
    private static File inner = null;
    private static File ext = null;
    private static boolean inited = false;

    public static void init(Context c) {
        if (c == null) return;
        synchronized (LOCK) {
            if (inited && appCtx != null) return;
            try {
                appCtx = c.getApplicationContext();
                inner = new File(appCtx.getFilesDir(), FILE);
                File d = appCtx.getExternalFilesDir(null);
                ext = (d == null) ? null : new File(d, FILE);
                inited = true;
                i("HF_LOG", "log file ready: " + inner.getAbsolutePath()
                        + (ext != null ? " | " + ext.getAbsolutePath() : ""));
            } catch (Throwable t) {
                android.util.Log.e("HF_LOG", "init err: " + t);
            }
        }
    }

    public static String path(Context c) {
        init(c);
        return inner == null ? "(未初始化)" : inner.getAbsolutePath();
    }

    public static String extPath(Context c) {
        init(c);
        return ext == null ? "(无外部目录)" : ext.getAbsolutePath();
    }

    // ---------------------------------------------------------------- 输出

    public static void i(String tag, String msg) {
        Log.println(Log.INFO, tag, msg);
        append("I", tag, msg);
    }

    public static void w(String tag, String msg) {
        Log.println(Log.WARN, tag, msg);
        append("W", tag, msg);
    }

    public static void e(String tag, String msg) {
        Log.println(Log.ERROR, tag, msg);
        append("E", tag, msg);
    }

    public static void e(String tag, String msg, Throwable t) {
        String full = msg + (t == null ? "" : " :: " + Log.getStackTraceString(t));
        Log.println(Log.ERROR, tag, full);
        append("E", tag, full);
    }

    private static void append(String lvl, String tag, String msg) {
        if (!inited || appCtx == null) return;
        synchronized (LOCK) {
            String line;
            try {
                line = TS.format(new Date()) + " " + lvl + "/" + tag + ": " + msg
                        + (msg.endsWith("\n") ? "" : "\n");
            } catch (Throwable t) {
                return;
            }
            writeTo(inner, line);
            writeTo(ext, line);
        }
    }

    private static void writeTo(File f, String line) {
        if (f == null) return;
        try {
            if (f.length() > MAX_BYTES) {
                // 超过上限：丢掉前半段，保留最近内容
                dropFirstHalf(f);
            }
            FileOutputStream out = new FileOutputStream(f, true);
            out.write(line.getBytes("UTF-8"));
            out.close();
        } catch (Throwable ignore) { }
    }

    /** 保留后半段，避免日志无限增长。 */
    private static void dropFirstHalf(File f) {
        try {
            long keep = f.length() / 2;
            RandomAccessFile raf = new RandomAccessFile(f, "rw");
            byte[] tail = new byte[(int) keep];
            raf.seek(f.length() - keep);
            raf.readFully(tail);
            raf.setLength(0);
            raf.seek(0);
            raf.write("---- 日志超过 512KB，已截断保留最近一半 ----\n".getBytes("UTF-8"));
            raf.write(tail);
            raf.close();
        } catch (Throwable ignore) { }
    }

    // ---------------------------------------------------------------- 读取

    /** 取最近的日志文本（最多 maxLines 行）。 */
    public static String read(Context c, int maxLines) {
        init(c);
        if (inner == null) return "(未初始化)";
        try {
            if (!inner.exists()) return "(还没有日志)";
            RandomAccessFile raf = new RandomAccessFile(inner, "r");
            long len = raf.length();
            long start = Math.max(0, len - 200 * 1024);   // 最多读尾部 200KB
            raf.seek(start);
            byte[] buf = new byte[(int) (len - start)];
            raf.readFully(buf);
            raf.close();
            String all = new String(buf, "UTF-8");
            if (start > 0) {
                int nl = all.indexOf('\n');
                if (nl > 0) all = all.substring(nl + 1);
            }
            String[] lines = all.split("\n");
            if (lines.length <= maxLines) return all;
            StringBuilder sb = new StringBuilder();
            for (int i = lines.length - maxLines; i < lines.length; i++) {
                sb.append(lines[i]).append('\n');
            }
            return sb.toString();
        } catch (Throwable t) {
            return "(读取失败: " + t + ")";
        }
    }

    public static void clear(Context c) {
        init(c);
        synchronized (LOCK) {
            if (inner != null) {
                try { inner.delete(); } catch (Throwable ignore) { }
            }
            if (ext != null) {
                try { ext.delete(); } catch (Throwable ignore) { }
            }
        }
        i("HF_LOG", "log cleared");
    }
}
