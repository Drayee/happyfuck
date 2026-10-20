/*
 * 抓取真实 upload 请求体 —— 为 HappyFuck 对齐字段结构
 *
 * 用法：
 *   frida -U -f com.ledreamer.zz -l capture_upload.js
 *   然后在 App 里正常自由跑一次并结束上传。
 *
 * 会在 logcat/控制台打印：
 *   1) SecurityRequestBodyConverter 的明文 JSON（上传 DTO 的真实字段和类型）
 *   2) envelope 后的 {t, pyd}
 *   3) 实际 HTTP 请求（url + headers）
 * 把明文 JSON 复制回 data/upload_sample.json 即可对齐。
 */

'use strict';

function dump(tag, obj) {
    try {
        var s = (typeof obj === 'string') ? obj : JSON.stringify(obj);
        console.log('\n===== ' + tag + ' =====');
        console.log(s);
        console.log('===== end ' + tag + ' =====\n');
    } catch (e) {
        console.log(tag + ' dump fail: ' + e);
    }
}

Java.perform(function () {
    // 1) 抓上传 DTO 明文：Gson 序列化后、AES 加密前
    try {
        var SBC = Java.use('com.legym.security.SecurityRequestBodyConverter');
        SBC.convert.implementation = function (t) {
            var out = this.convert(t);
            try {
                var cls = t.getClass().getName();
                if (cls.indexOf('UploadRunInfo') >= 0 ||
                    cls.indexOf('RunInfoReq') >= 0) {
                    // 用 Gson 把对象转成 JSON 打印
                    var Gson = Java.use('com.google.gson.Gson');
                    var g = Gson.$new();
                    dump('UPLOAD_PLAIN (' + cls + ')', g.toJson(t));
                }
            } catch (e) {
                console.log('gson dump fail: ' + e);
            }
            return out;
        };
        console.log('[hook] SecurityRequestBodyConverter.convert OK');
    } catch (e) {
        console.log('[hook] SBC fail: ' + e);
    }

    // 2) 抓 encodeNs 的输入（明文）和输出（pyd）
    try {
        var NL = Java.use('com.legym.security.NativeLib');
        NL.encodeNs.implementation = function (str, ts) {
            var out = this.encodeNs(str, ts);
            if (str && str.indexOf('routineLine') >= 0) {
                dump('encodeNs IN (upload plain)', str);
                dump('encodeNs ts', ts);
                dump('encodeNs OUT (pyd head)', out.substring(0, 120));
            }
            return out;
        };
        console.log('[hook] NativeLib.encodeNs OK');
    } catch (e) {
        console.log('[hook] encodeNs fail: ' + e);
    }

    // 3) 抓真实 HTTP：OkHttp Interceptor
    try {
        var Interceptor = Java.registerClass({
            name: 'com.happyfuck.Cap',
            implements: [Java.use('okhttp3.Interceptor')],
            methods: {
                intercept: function (chain) {
                    var req = chain.request();
                    var url = req.url().toString();
                    if (url.indexOf('upload') >= 0 ||
                        url.indexOf('getRunningRange') >= 0 ||
                        url.indexOf('getRunningLimit') >= 0) {
                        dump('HTTP ' + req.method() + ' ' + url,
                             JSON.stringify({
                                headers: req.headers().toString(),
                             }));
                        var body = req.body();
                        try {
                            var Buffer = Java.use('okio.Buffer');
                            var buf = Buffer.$new();
                            body.writeTo(buf);
                            dump('HTTP BODY', buf.readUtf8());
                        } catch (e) {
                            console.log('body read fail: ' + e);
                        }
                    }
                    return chain.proceed(req);
                }
            }
        });
        console.log('[hook] OkHttp interceptor class built (manual add needed)');
    } catch (e) {
        console.log('[hook] okhttp fail: ' + e);
    }

    // 3) 抓 kernel 栈加密（upload 走这条）：f.m.b.h.a.b(bytes, key) + c(ts)->key
    try {
        var KA = Java.use('f.m.b.h.a');
        KA.b.implementation = function (bytes, key) {
            var out = this.b(bytes, key);
            try {
                var plain = Java.use('java.lang.String').$new(bytes, 'UTF-8');
                if (plain.indexOf('routineLine') >= 0) {
                    dump('KERNEL-PLAIN', plain.toString());
                    dump('KERNEL-KEY', key);
                    dump('KERNEL-PYD-HEAD', out.substring(0, 80));
                }
            } catch (e) { console.log('kernel dump fail: ' + e); }
            return out;
        };
        KA.c.implementation = function (j) {
            var out = this.c(j);
            console.log('[kernel] c(' + j + ') = ' + out);
            return out;
        };
        console.log('[hook] kernel f.m.b.h.a.b/c OK');
    } catch (e) {
        console.log('[hook] kernel fail: ' + e);
    }

    // 4) 抓 signRunData 的输入输出（VO 被改写了什么）
    try {
        var NL2 = Java.use('com.legym.security.NativeLib');
        NL2.signRunData.implementation = function (obj, id, school) {
            this.signRunData(obj, id, school);
            try {
                var Gson = Java.use('com.google.gson.Gson');
                dump('AFTER signRunData', Gson.$new().toJson(obj));
                dump('signRunData args', JSON.stringify({id: id, school: school}));
            } catch (e) { console.log('vo dump fail: ' + e); }
        };
        console.log('[hook] signRunData OK');
    } catch (e) {
        console.log('[hook] signRunData fail: ' + e);
    }

    console.log('[capture] ready. 现在在 App 里自由跑一次并上传。');
});
