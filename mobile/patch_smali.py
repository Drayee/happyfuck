#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 手机版 —— smali / so 层补丁（幂等，可重复执行）。

设计目标：`apktool d -f` 重新解码后，跑一次本脚本即可把全部补丁打回去。
所有补丁都带「已应用」检测，重复执行不会叠加。

补丁清单：
  P1  libsecurity.so  checkSignature 证书绑定绕过（arm64 @0x7ae4: b.ne -> nop）
  P2  LocationService.onCreate        加载轨迹 + 启动驱动
  P3  LocationService.onLocationChanged 注入合成 GPS
  P4  LocationService.r0()            不启动真实高德定位（startLocation -> nop）
  P5  LocationService.onDestroy       停止驱动
  P6  UniversityApplication$a.e()     App 启动即加载轨迹
  P7  RunningViewModel.n()            hs() 返回 null 时回退空串（避免 NPE）
  P8  PermissionUtil                 定位权限/服务判定恒真（消除误弹窗）
  P9  NativeProbe.smali               原生探针（诊断用，可选）

用法：
    python mobile/patch_smali.py            # 应用全部补丁
    python mobile/patch_smali.py --check    # 只检查状态
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APKTOOL = os.environ.get('APKTOOL_OUT') or os.path.join(ROOT, 'unpacked', 'apktool_out')

SVC = os.path.join(APKTOOL, 'smali_classes3', 'com', 'ledreamer',
                   'runningModule', 'service', 'LocationService.smali')
APP = os.path.join(APKTOOL, 'smali_classes3', 'com', 'ledreamer', 'zz',
                   'UniversityApplication$a.smali')
VM = os.path.join(APKTOOL, 'smali_classes3', 'com', 'ledreamer', 'zz',
                  'activity', 'running', 'viewmodel', 'RunningViewModel.smali')
PERM = os.path.join(APKTOOL, 'smali_classes4', 'io', 'dcloud', 'common',
                    'adapter', 'util', 'PermissionUtil.smali')
PROBE_DIR = os.path.join(APKTOOL, 'smali_classes6', 'com', 'ledreamer', 'hf')
PROBE = os.path.join(PROBE_DIR, 'NativeProbe.smali')
RUN_ACT = os.path.join(APKTOOL, 'smali_classes3', 'com', 'ledreamer', 'zz',
                       'activity', 'running', 'RunningActivity.smali')
SEC_SO = os.path.join(APKTOOL, 'lib', 'arm64-v8a', 'libsecurity.so')

results = []


def log(tag, msg):
    results.append((tag, msg))
    print('[%s] %s' % (tag, msg))


def read(p):
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()


def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(s)


def patch_text(path, name, marker, old, new):
    """幂等文本替换：marker 存在则跳过。"""
    if not os.path.exists(path):
        log('FAIL', '%s 文件不存在: %s' % (name, path))
        return False
    s = read(path)
    if marker in s:
        log('skip', '%s 已应用' % name)
        return True
    if old not in s:
        log('FAIL', '%s 锚点未找到' % name)
        return False
    write(path, s.replace(old, new, 1))
    log('ok', name)
    return True


# ---------------------------------------------------------------- P1 .so
def patch_libsecurity():
    path = SEC_SO
    if not os.path.exists(path):
        log('FAIL', 'libsecurity.so 不存在')
        return False
    data = bytearray(open(path, 'rb').read())

    CMP_W19_W8 = 0x6B08027F     # cmp w19, w8
    B_NE       = 0x540000A1     # b.ne
    NOP        = 0xD503201F

    pat = struct.pack('<I', CMP_W19_W8)
    idx = data.find(pat)
    while idx >= 0:
        nxt = idx + 4
        if nxt + 4 <= len(data):
            w = struct.unpack_from('<I', data, nxt)[0]
            if w == NOP:
                log('skip', 'libsecurity checkSignature 已 nop')
                return True
            if w == B_NE:
                struct.pack_into('<I', data, nxt, NOP)
                open(path, 'wb').write(data)
                log('ok', 'libsecurity checkSignature b.ne -> nop @file+0x%x' % nxt)
                return True
        idx = data.find(pat, idx + 1)

    log('FAIL', 'libsecurity: 找不到 cmp w19,w8 + b.ne 组合')
    return False


# ---------------------------------------------------------------- P2~P5
def patch_location_service():
    ok = True

    # P2 onCreate: f0() 之后加载轨迹 + 起驱动
    ok &= patch_text(
        SVC, 'LocationService.onCreate', 'SyntheticGps;->load',
        """    .line 2
    invoke-virtual {p0}, Lcom/ledreamer/runningModule/service/LocationService;->f0()V

    const/4 v0, 0x1""",
        """    .line 2
    invoke-virtual {p0}, Lcom/ledreamer/runningModule/service/LocationService;->f0()V

    invoke-static {p0}, Lcom/ledreamer/hf/SyntheticGps;->load(Landroid/content/Context;)V

    invoke-static {p0}, Lcom/ledreamer/hf/SyntheticGps;->startDriver(Landroid/content/Context;)V

    const/4 v0, 0x1""")

    # P3 onLocationChanged: 入口注入
    s = read(SVC) if os.path.exists(SVC) else ''
    if 'SyntheticGps;->inject' in s:
        log('skip', 'LocationService.onLocationChanged 已应用')
    else:
        # 先把 .locals 7 -> 8（若还是 7）
        if '.method public onLocationChanged(Lcom/amap/api/location/AMapLocation;)V\n    .locals 7' in s:
            s = s.replace(
                '.method public onLocationChanged(Lcom/amap/api/location/AMapLocation;)V\n    .locals 7',
                '.method public onLocationChanged(Lcom/amap/api/location/AMapLocation;)V\n    .locals 8', 1)
        old = """    const-string v1, "aMapLocation"

    invoke-static {p1, v1}, Lkotlin/jvm/internal/Intrinsics;->checkNotNullParameter(Ljava/lang/Object;Ljava/lang/String;)V

    .line 1
    :try_start_0"""
        new = """    const-string v1, "aMapLocation"

    invoke-static {p1, v1}, Lkotlin/jvm/internal/Intrinsics;->checkNotNullParameter(Ljava/lang/Object;Ljava/lang/String;)V

    sget-boolean v7, Lcom/ledreamer/hf/SyntheticGps;->enabled:Z

    if-eqz v7, :hf_orig

    invoke-static {p1}, Lcom/ledreamer/hf/SyntheticGps;->inject(Lcom/amap/api/location/AMapLocation;)V

    :hf_orig

    .line 1
    :try_start_0"""
        if old in s:
            write(SVC, s.replace(old, new, 1))
            log('ok', 'LocationService.onLocationChanged 注入')
        else:
            log('FAIL', 'LocationService.onLocationChanged 锚点未找到')
            ok = False

    # P4 r0(): startLocation -> nop
    ok &= patch_text(
        SVC, 'LocationService.r0 startLocation->nop', 'HF: 不启动真实高德定位',
        """    .line 16
    invoke-virtual {v1}, Lcom/amap/api/location/AMapLocationClient;->startLocation()V""",
        """    .line 16
    # HF: 不启动真实高德定位，改用 SyntheticGps 驱动（避免模拟器/室内无效坐标污染）
    nop""")

    # P5 onDestroy: stopDriver
    ok &= patch_text(
        SVC, 'LocationService.onDestroy', 'SyntheticGps;->stopDriver',
        """.method public onDestroy()V
    .locals 3

    .line 1""",
        """.method public onDestroy()V
    .locals 3

    invoke-static {}, Lcom/ledreamer/hf/SyntheticGps;->stopDriver()V

    .line 1""")
    return ok


# ---------------------------------------------------------------- P6
def patch_application():
    return patch_text(
        APP, 'UniversityApplication$a.e load', 'SyntheticGps;->load',
        """    invoke-static {v1}, Lcom/legym/security/NativeLib;->checkSignature(Ljava/lang/Object;)I

    .line 4""",
        """    invoke-static {v1}, Lcom/legym/security/NativeLib;->checkSignature(Ljava/lang/Object;)I

    invoke-static {v1}, Lcom/ledreamer/hf/SyntheticGps;->load(Landroid/content/Context;)V

    .line 4""")


# ---------------------------------------------------------------- P7
def patch_viewmodel():
    return patch_text(
        VM, 'RunningViewModel.n hs null fallback', 'hf_sign_ok',
        """    invoke-static {v0}, Lcn/legym/ai/util/Rengis;->hs(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    const-string v1, "hs(key)\"""",
        """    invoke-static {v0}, Lcn/legym/ai/util/Rengis;->hs(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    if-nez v0, :hf_sign_ok

    const-string v0, ""

    const-string v1, "HF_SIGN"

    const-string v2, "hs() returned null -> fallback empty signDigital"

    invoke-static {v1, v2}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I

    :hf_sign_ok

    const-string v1, "hs(key)\"""")


# ---------------------------------------------------------------- P11
def patch_perm_gate():
    """RunningActivity.K() / M()：跑步页的定位权限门禁 -> 恒真。

    背景：App 开跑前检查 ACCESS_FINE_LOCATION，未授权就弹
    「此功能需要您授权定位权限」并中断。但本项目 GPS 完全由
    SyntheticGps 合成注入，不需要真实定位；且唯一真正需要权限的调用
    (LocationManager.requestLocationUpdates, RunningActivity:1253)
    外层已有 try/catch，没权限只会被捕获记日志，不会崩。
    """
    ok = True
    for sig, name in (('.method public final K()Z', 'K'),
                      ('.method public final M()Z', 'M')):
        marker = 'HF_NOPERM_' + name
        s = read(RUN_ACT)
        if marker in s:
            log('skip', 'RunningActivity.%s 门禁已恒真' % name)
            continue
        i = s.find(sig)
        if i < 0:
            log('FAIL', 'RunningActivity.%s 未找到' % name)
            ok = False
            continue
        j = s.find('.end method', i)
        if j < 0:
            log('FAIL', 'RunningActivity.%s 缺少 .end method' % name)
            ok = False
            continue
        j += len('.end method')
        new = (sig + '\n'
               '    .locals 1\n\n'
               '    # ' + marker + ': 定位权限门禁恒真\n'
               '    const/4 v0, 0x1\n\n'
               '    return v0\n'
               '.end method')
        write(RUN_ACT, s[:i] + new + s[j:])
        log('ok', 'RunningActivity.%s 门禁已改为恒真' % name)
    return ok


# ---------------------------------------------------------------- P10
def patch_capture_extras():
    """在 RunningActivity.initData() 里捕获 Intent 参数，供每日自动跑回放。"""
    return patch_text(
        RUN_ACT, 'RunningActivity.initData captureExtras', 'captureIntentExtras',
        """.method public final initData()V
    .locals 2

    .line 1
    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;""",
        """.method public final initData()V
    .locals 2

    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;

    move-result-object v0

    invoke-static {p0, v0}, Lcom/ledreamer/hf/HfAutoRun;->captureIntentExtras(Landroid/content/Context;Landroid/content/Intent;)V

    .line 1
    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;""")


# ---------------------------------------------------------------- P8
def patch_permission():
    ok = patch_text(
        PERM, 'PermissionUtil.checkLocationPermission', 'HF: 定位权限判定恒真',
        """.method public static checkLocationPermission(Landroid/app/Activity;)Z
    .locals 3
""",
        """.method public static checkLocationPermission(Landroid/app/Activity;)Z
    .locals 3

    # HF: 定位权限判定恒真，避免部分 ROM 误判导致模态框阻断刷课
    const/4 v0, 0x1

    return v0
""")
    ok &= patch_text(
        PERM, 'PermissionUtil.checkLocationService', 'HF: 定位服务判定恒真',
        """.method public static checkLocationService(Landroid/app/Activity;)Z
    .locals 3
""",
        """.method public static checkLocationService(Landroid/app/Activity;)Z
    .locals 3

    # HF: 定位服务判定恒真（合成 GPS 不需要真实 provider）
    const/4 v1, 0x1

    return v1
""")
    return ok


# ---------------------------------------------------------------- P9
PROBE_SRC = '''.class public Lcom/ledreamer/hf/NativeProbe;
.super Ljava/lang/Object;
.source "NativeProbe.java"


.method public static constructor <clinit>()V
    .locals 0
    return-void
.end method

.method public constructor <init>()V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    return-void
.end method

.method public static probe()V
    .locals 5

    const-string v0, "1712345678901"

    invoke-static {v0}, Lcom/legym/security/NativeLib;->getDyKey(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v1

    const-string v2, "HF_DYKEY"

    invoke-static {v2, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    return-void
.end method
'''


def patch_probe():
    if os.path.exists(PROBE):
        log('skip', 'NativeProbe.smali 已存在')
        return True
    write(PROBE, PROBE_SRC)
    log('ok', 'NativeProbe.smali 已写入')
    return True


def main():
    check_only = '--check' in sys.argv
    if not os.path.isdir(APKTOOL):
        print('[FAIL] 找不到 apktool_out，先执行 apktool d')
        return 1

    if check_only:
        # 只报告
        pairs = [
            ('libsecurity', SEC_SO, None),
            ('LocationService.onLocationChanged', SVC, 'SyntheticGps;->inject'),
            ('LocationService.onCreate', SVC, 'SyntheticGps;->load'),
            ('LocationService.r0', SVC, 'HF: 不启动真实高德定位'),
            ('LocationService.onDestroy', SVC, 'SyntheticGps;->stopDriver'),
            ('UniversityApplication.e', APP, 'SyntheticGps;->load'),
            ('RunningViewModel.n', VM, 'hf_sign_ok'),
            ('PermissionUtil.checkLocationPermission', PERM, 'HF: 定位权限判定恒真'),
            ('PermissionUtil.checkLocationService', PERM, 'HF: 定位服务判定恒真'),
            ('RunningActivity.initData captureExtras', RUN_ACT, 'captureIntentExtras'),
            ('RunningActivity.K 权限门禁恒真', RUN_ACT, 'HF_NOPERM_K'),
            ('RunningActivity.M 后台定位门禁恒真', RUN_ACT, 'HF_NOPERM_M'),
            ('NativeProbe', PROBE, None),
        ]
        for name, path, marker in pairs:
            if marker is None:
                st = 'OK' if os.path.exists(path) else 'MISSING'
            else:
                st = 'OK' if (os.path.exists(path) and marker in read(path)) else 'TODO'
            print('  %-42s %s' % (name, st))
        return 0

    ok = True
    ok &= patch_libsecurity()
    ok &= patch_location_service()
    ok &= patch_application()
    ok &= patch_viewmodel()
    ok &= patch_permission()
    ok &= patch_capture_extras()
    ok &= patch_perm_gate()
    ok &= patch_probe()

    print('')
    if ok:
        print('全部补丁就绪')
        return 0
    print('有补丁失败，请检查上面的 FAIL 行')
    return 1


if __name__ == '__main__':
    sys.exit(main())
