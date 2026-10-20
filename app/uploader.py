#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 乐奸 —— 上传模块（真实账号实测打通，2026-10-20）。

实测结论（上传 running/app/v3/upload 返回 code=0 + 记录ID）：
  ✅ 上传走 **明文 JSON**，不需要 envelope
  ✅ startTime / endTime / signTime 必须是 "yyyy-MM-dd HH:mm:ss" 字符串
     —— 传毫秒字符串会让整个对象解析失败，报「所有字段 must not be null」
  ✅ endTimeDate 是 long（毫秒）
  ✅ 当前学期 hasRule=false 时，signDigital 传空服务端接受
  ✅ 登录同样不校验 signDigital（见 service.py，仍用 native salt envelope）

字段类型（对齐 UploadRunInfoReqVo smali）：
  effectiveMileage/gpsMileage/totalMileage/totalPart/avePace = double
  effectivePart/paceNumber/keepTime/scoringType/paceRange/calorie = int
  startTime/endTime/signTime/type/oct/... = String
  endTimeDate = long
"""
import base64
import datetime
import json
import os
import time

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

BASE = 'https://cpes.legym.cn/'
NATIVE_SALT = '402881ea7c39c5d5017c39d143a8062b'   # libsecurity getNetSalt
KERNEL_SALT = 'cee1833ccb83418092ebd3f113cbd9c8'   # f.m.b.h.a.c 里的 salt

TIME_FMT = '%Y-%m-%d %H:%M:%S'

# 时间字段：服务端要格式化字符串
TIME_KEYS = ('startTime', 'endTime', 'signTime')


def fmt_time(ms):
    """毫秒时间戳 -> 'yyyy-MM-dd HH:mm:ss'。"""
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime(TIME_FMT)


def normalize_vo(vo):
    """把 run_sim 生成的毫秒时间戳转成服务端要的格式。"""
    out = dict(vo)
    for k in TIME_KEYS:
        v = out.get(k)
        if isinstance(v, int) or (isinstance(v, str) and v.lstrip('-').isdigit()):
            out[k] = fmt_time(int(v))
    if isinstance(out.get('endTimeDate'), str) and out['endTimeDate'].lstrip('-').isdigit():
        out['endTimeDate'] = int(out['endTimeDate'])
    return out


def dyn_key(ts_ms, salt):
    """复刻 f.m.b.h.a.c / NativeLib.getDyKey 的密钥派生。"""
    s = str(int(ts_ms))
    n = abs(int(s[2:5]) - int(s[4:8])) << int(s[-1])
    return ('%d%s' % (n, salt)).encode()[:16]


def enc_body(plain, ts_ms, salt=KERNEL_SALT):
    """加密（登录等仍需要）。"""
    k = dyn_key(ts_ms, salt)
    return base64.b64encode(
        AES.new(k, AES.MODE_ECB).encrypt(pad(plain.encode('utf-8'), 16))
    ).decode()


def dec_body(b64, ts_ms, salt=KERNEL_SALT):
    k = dyn_key(ts_ms, salt)
    return unpad(AES.new(k, AES.MODE_ECB).decrypt(base64.b64decode(b64)),
                 16).decode('utf-8', 'replace')


def upload(access_token, school_id, vo, timeout=20, sign_digital=None):
    """明文上传。返回 dict：{ok, code, message, record_id}。"""
    import urllib.request
    import urllib.error

    body = normalize_vo(vo)
    if sign_digital is not None:
        body['signDigital'] = sign_digital

    req = urllib.request.Request(
        BASE + 'running/app/v3/upload',
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json; charset=UTF-8',
                 'charset': 'UTF-8',
                 'User-Agent': 'okhttp/4.9.3',
                 'Authorization': 'Bearer ' + access_token,
                 'Organization': str(school_id)},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        txt = e.read().decode('utf-8', 'replace')
    except Exception as e:
        return {'ok': False, 'code': -1, 'message': '网络: %s' % e}

    try:
        o = json.loads(txt)
    except Exception:
        return {'ok': False, 'code': -2, 'message': txt[:200]}

    code = o.get('code')
    msg = o.get('message') or ''
    return {'ok': code == 0, 'code': code, 'message': msg, 'mode': 'plain',
            'record_id': o.get('data') if code == 0 else None}


# 兼容旧调用（service.py 可能传 start_ms/end_ms）
def upload_legacy(access_token, school_id, vo, start_ms, end_ms, salt=None,
                  use_sample=True, timeout=20):
    return upload(access_token, school_id, vo, timeout=timeout)
