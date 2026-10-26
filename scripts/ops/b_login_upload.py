#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
乐健体育 (com.ledreamer.zz) —— 纯脚本 登录 -> 续期 -> 上传 全链路

链路来源（静态逆向确认）:
  登录   POST https://cpes.legym.cn/authorization/user/v2/manage/login
         body = LoginReqBean{userName, password, signDigital, phone, entrance}
         signDigital = Rengis.hs(userName + password + entrance)
         resp = UniUserInfoBean{ id, schoolId, limitationsGoalsSexInfoId, accessToken, refreshToken, ... }
  续期   GET  https://cpes.legym.cn/authorization/user/refreshToken?refreshToken=XXX
         header Authorization: Bearer <accessToken>
         resp = AuthorTokenRespBean{accessToken, accessTokenExpires, refreshToken, tokenType}
  上传   POST https://cpes.legym.cn/running/app/v3/upload
         header Authorization: Bearer <accessToken>
         header Organization: <schoolId>
         body = UploadRunInfoReqVo (envelope 加密)

加密信封（tools/legym_envelope.py 已实现并验证）:
    {"t": <ms>, "pyd": b64(AES-128-ECB-PKCS5(json, getDyKey(str(t))))}

唯一无法纯 Python 计算的环节: Rengis.hs() —— DexVMP 动态类，不在任何 dex 中。
本脚本用 HsProvider 抽象它，三种实现:
  1) FridaRpcHs    : 连真机 frida server，RPC 调 Java.perform 里的 Rengis.hs   [全自动]
  2) StaticTableHs : 预先抓好的 {输入: 输出} JSON 表                            [半自动]
  3) None          : 只跑登录/续期，上传时跳过（先验证账号链路）                [调试]

用法:
    # 只验证登录 + 续期（不需要 hs 表里已有值，但登录本身需要 hs）
    python b_login_upload.py login --phone 138xxxx --password xxx --entrance 1 \
        --hs-mode table --hs-table hs_table.json

    # 全自动：frida RPC 签名
    python b_login_upload.py run --phone 138xxxx --password xxx \
        --hs-mode frida --frida-host 127.0.0.1:27042
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from legym_envelope import wrap_request, unwrap_response  # noqa: E402
BASE = 'https://cpes.legym.cn/'
UA = 'okhttp/4.9.3'


# --------------------------------------------------------------------------
# hs() 提供者
# --------------------------------------------------------------------------
class HsProvider:
    """Rengis.hs(String) -> String 的抽象。"""

    def hs(self, s: str) -> str:
        raise NotImplementedError


class StaticTableHs(HsProvider):
    """从 JSON 表读 {明文: 签名}。hs 是纯函数，同输入必同输出。"""

    def __init__(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            self.table = json.load(f)

    def hs(self, s: str) -> str:
        if s not in self.table:
            raise KeyError(
                'hs() 表里没有这个输入:\n  %r\n'
                '在真机上跑一次抓取脚本补进去，或改用 --hs-mode frida。' % s)
        return self.table[s]


class FridaRpcHs(HsProvider):
    """连 frida server，RPC 调用 Rengis.hs。需要真机 + frida-server。"""

    def __init__(self, host: str = '127.0.0.1:27042'):
        import frida  # 延迟导入
        self.device = frida.get_device_manager().add_remote_device(host)
        self.session = self.device.attach('com.ledreamer.zz')
        self.script = self.session.create_script(HS_AGENT)
        self.script.load()
        self.script.on('message', lambda m, d: None)

    def hs(self, s: str) -> str:
        return self.script.exports_sync.hs(s)


HS_AGENT = r'''
Java.perform(function () {
    var R = Java.use('cn.legym.ai.util.Rengis');
    rpc.exports = {
        hs: function (s) { return R.hs(s); }
    };
});
'''


# --------------------------------------------------------------------------
# HTTP 层
# --------------------------------------------------------------------------
class _Resp(object):
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


def _session():
    """纯标准库，无第三方依赖。"""
    return {'cookie': None}


def _request(method, url, headers=None, data=None, timeout=20):
    import urllib.request
    import urllib.error
    h = {'User-Agent': UA}
    if headers:
        h.update(headers)
    body = data.encode('utf-8') if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _Resp(r.status, r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        return _Resp(e.code, e.read().decode('utf-8', 'replace'))
    except urllib.error.URLError as e:
        return _Resp(0, '{"_error":"%s"}' % e.reason)


def _post_envelope(sess, path: str, body_obj, extra_headers=None):
    """按 App 的方式发一个 @SecurityAes 加密请求。"""
    ts = int(time.time() * 1000)
    env = wrap_request(json.dumps(body_obj, ensure_ascii=False, separators=(',', ':')), ts)
    headers = {'Content-Type': 'application/json; charset=UTF-8'}
    if extra_headers:
        headers.update(extra_headers)
    r = _request('POST', BASE + path, headers=headers, data=json.dumps(env))
    return _parse(r)


def _get_envelope(sess, path: str, params=None, extra_headers=None):
    import urllib.parse
    url = BASE + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    headers = {'Content-Type': 'application/json; charset=UTF-8'}
    if extra_headers:
        headers.update(extra_headers)
    r = _request('GET', url, headers=headers)
    return _parse(r)


def _parse(r):
    """服务端可能返回加密信封，也可能直接明文；两种都兜住。"""
    text = r.text
    try:
        obj = json.loads(text)
    except Exception:
        return {'_http': r.status_code, '_raw': text}
    if isinstance(obj, dict) and 'pyd' in obj and 't' in obj:
        try:
            plain = unwrap_response(obj)
            return json.loads(plain)
        except Exception:
            return {'_http': r.status_code, '_raw': text, '_envelope': obj}
    return obj


# --------------------------------------------------------------------------
# 业务动作
# --------------------------------------------------------------------------
def do_login(sess, hs: HsProvider, phone: str, password: str, entrance: str = '1'):
    """POST authorization/user/v2/manage/login"""
    sign_input = phone + password + entrance
    sign = hs.hs(sign_input)
    body = {
        'userName': phone,          # App 里是 setUserName(getPhone())
        'password': password,
        'signDigital': sign,
        'phone': phone,
        'entrance': entrance,
    }
    data = _post_envelope(sess, 'authorization/user/v2/manage/login', body)
    print('[login] resp =', json.dumps(data, ensure_ascii=False)[:800])
    return data


def do_refresh(sess, access_token: str, refresh_token: str):
    """GET authorization/user/refreshToken"""
    data = _get_envelope(
        sess,
        'authorization/user/refreshToken',
        params={'refreshToken': refresh_token},
        extra_headers={'Authorization': 'Bearer ' + access_token},
    )
    print('[refresh] resp =', json.dumps(data, ensure_ascii=False)[:500])
    return data


def build_upload_vo(cfg: dict) -> dict:
    """按 UploadRunInfoReqVo 字段名构造上传体。字段清单来自 jadx 的 @Metadata d2。"""
    return {
        'effectiveMileage': cfg['effectiveMileage'],
        'effectivePart': cfg['effectivePart'],
        'startTime': cfg['startTime'],
        'calorie': cfg['calorie'],
        'avePace': cfg['avePace'],
        'keepTime': cfg['keepTime'],
        'paceNumber': cfg['paceNumber'],
        'totalMileage': cfg['totalMileage'],
        'totalPart': cfg['totalPart'],
        'endTime': cfg['endTime'],
        'gpsMileage': cfg.get('gpsMileage', cfg['totalMileage']),
        'limitationsGoalsSexInfoId': cfg['limitationsGoalsSexInfoId'],
        'scoringType': cfg['scoringType'],
        'semesterId': cfg['semesterId'],
        'routineLine': cfg.get('routineLine', []),
        'signPoint': cfg.get('signPoint', []),
        'type': cfg.get('type', '1'),
        'uneffectiveReason': cfg.get('uneffectiveReason', ''),
        'systemVersion': cfg.get('systemVersion', '13'),
        'appVersion': cfg.get('appVersion', '3.10.3'),
        'deviceType': cfg.get('deviceType', 'android'),
        'signTime': cfg.get('signTime', cfg['startTime']),
        'oct': cfg.get('oct', ''),
        'endTimeDate': cfg.get('endTimeDate', cfg['endTime']),
        'paceRange': cfg.get('paceRange', 0.0),
    }


def sign_input_of(vo: dict) -> str:
    """复刻 RunningViewModel.java:234 的拼接顺序。"""
    return (
        str(vo['effectiveMileage'])
        + str(vo['effectivePart'])
        + str(vo['startTime'])
        + str(vo['calorie'])
        + str(int(float(vo['avePace'])))
        + str(vo['keepTime'])
        + str(vo['paceNumber'])
        + str(vo['totalMileage'])
        + str(int(float(vo['totalPart'])))
    )


def do_upload(sess, hs: HsProvider, access_token: str, school_id: str, vo: dict,
              ruleset=None, force=False):
    """POST running/app/v3/upload

    ruleset: 传入 rules.RuleSet 时先做规则体检，有硬问题就拦下。
    force:   为 True 时即使体检不通过也照传。
    """
    vo = dict(vo)

    if ruleset is not None:
        ok, probs, warns = ruleset.check(vo)
        for w in warns:
            print('[check] 提示:', w)
        if probs:
            for p in probs:
                print('[check] 问题:', p)
            if not force:
                sys.exit('[check] 体检不通过，已中止上传（加 --force 可强制）')
        else:
            print('[check] 规则体检通过')

    vo['signDigital'] = hs.hs(sign_input_of(vo))
    data = _post_envelope(
        sess,
        'running/app/v3/upload',
        vo,
        extra_headers={
            'Authorization': 'Bearer ' + access_token,
            'Organization': str(school_id),
        },
    )
    print('[upload] resp =', json.dumps(data, ensure_ascii=False)[:800])
    return data


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def make_hs(args) -> HsProvider:
    if args.hs_mode == 'frida':
        return FridaRpcHs(args.frida_host)
    if args.hs_mode == 'table':
        if not args.hs_table or not os.path.exists(args.hs_table):
            sys.exit('--hs-mode table 需要 --hs-table 指向存在的 JSON 文件')
        return StaticTableHs(args.hs_table)
    sys.exit('未知 --hs-mode: %s' % args.hs_mode)


def main():
    ap = argparse.ArgumentParser(description='乐健 纯脚本 登录/续期/上传')
    ap.add_argument('action', choices=['login', 'refresh', 'upload', 'run'])
    ap.add_argument('--phone')
    ap.add_argument('--password')
    ap.add_argument('--entrance', default='1', help='登录入口标识，App 默认 "1"')
    ap.add_argument('--hs-mode', default='table', choices=['table', 'frida'])
    ap.add_argument('--hs-table', default='hs_table.json')
    ap.add_argument('--frida-host', default='127.0.0.1:27042')
    ap.add_argument('--access-token', help='已有 token 时跳过登录')
    ap.add_argument('--refresh-token')
    ap.add_argument('--school-id', help='Organization 头')
    ap.add_argument('--vo', help='上传体 JSON 文件（字段见 build_upload_vo）')
    ap.add_argument('--out', default='session.json', help='登录结果落盘')
    args = ap.parse_args()

    sess = _session()
    hs = make_hs(args)

    if args.action == 'login':
        if not (args.phone and args.password):
            sys.exit('login 需要 --phone --password')
        data = do_login(sess, hs, args.phone, args.password, args.entrance)
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print('[login] 已写入', args.out)
        return

    if args.action == 'refresh':
        if not (args.access_token and args.refresh_token):
            sys.exit('refresh 需要 --access-token --refresh-token')
        do_refresh(sess, args.access_token, args.refresh_token)
        return

    if args.action == 'upload':
        if not (args.access_token and args.school_id and args.vo):
            sys.exit('upload 需要 --access-token --school-id --vo')
        with open(args.vo, 'r', encoding='utf-8') as f:
            vo = json.load(f)
        do_upload(sess, hs, args.access_token, args.school_id, vo)
        return

    # run: 登录 -> 上传，一气呵成
    if not (args.phone and args.password):
        sys.exit('run 需要 --phone --password')
    data = do_login(sess, hs, args.phone, args.password, args.entrance)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    payload = data.get('data') or data
    token = payload.get('accessToken') or payload.get('token')
    school = args.school_id or payload.get('schoolId') or payload.get('organizationId')
    if not token:
        sys.exit('登录返回里找不到 accessToken，检查 resp 结构')
    if not args.vo:
        print('[run] 没有 --vo，停在登录。token=', token[:24], '... school=', school)
        return
    if not school:
        sys.exit('拿不到 schoolId，请用 --school-id 指定')
    with open(args.vo, 'r', encoding='utf-8') as f:
        vo = json.load(f)
    do_upload(sess, hs, token, school, vo)


if __name__ == '__main__':
    main()
