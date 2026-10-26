#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量反作弊/完整性特征扫描（只读）。

扫描 apktool_out/smali* 下所有 .smali，按类别命中并聚合到包，
同时统计内部类（文件名含 $）分布。
输出: report/anticheat-scan.json
"""
import os
import re
import json
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APKTOOL = os.path.join(ROOT, 'apktool_out')
SMALI_DIRS = [d for d in os.listdir(APKTOOL) if d.startswith('smali')]

PATTERNS = {
    '签名校验': [
        (r'getPackageInfo', 'getPackageInfo'),
        (r'GET_SIGNATURES|getSignatures', '读签名'),
        (r'->signatures:', 'PackageInfo.signatures'),
        (r'checkSignature', 'checkSignature'),
        (r'UNSIGNATURE', 'UNSIGNATURE'),
    ],
    'Root检测': [
        (r'/system/xbin/su|/system/bin/su|/sbin/su', 'su 路径'),
        (r'magisk|Magisk', 'magisk'),
        (r'Superuser|superuser', 'superuser'),
        (r'test-keys', 'test-keys'),
        (r'ro\.debuggable|ro\.secure', 'debuggable 属性'),
    ],
    '模拟器检测': [
        (r'goldfish|ranchu', 'goldfish/ranchu'),
        (r'qemu|QEMU', 'qemu'),
        (r'generic_x86|generic_x86_64', 'generic x86'),
        (r'isEmulator|checkEmulator|EMULATOR', 'isEmulator'),
        (r'ro\.kernel\.qemu', 'qemu 属性'),
        (r'Bluestacks|bluestacks|Genymotion|genymotion|Nox|MEmu', '模拟器品牌'),
    ],
    '虚拟定位检测': [
        (r'isFromMockProvider', 'isFromMockProvider'),
        (r'setMock|->mock:', 'setMock'),
        (r'MockLocation|MOCK_LOCATION', 'MockLocation'),
        (r'isMock', 'isMock'),
    ],
    '调试/Hook检测': [
        (r'isDebuggerConnected', 'isDebuggerConnected'),
        (r'ptrace', 'ptrace'),
        (r'TracerPid', 'TracerPid'),
        (r'Xposed|LSPosed|EdXposed', 'Xposed'),
        (r'frida|Frida', 'frida'),
        (r'substrate|Substrate', 'substrate'),
        (r'/proc/self/maps', '/proc/self/maps'),
        (r'gum-|frida-agent', 'frida agent'),
    ],
    '完整性校验': [
        (r'getPackageCodePath|getSourceDir', 'apk 路径'),
        (r'MessageDigest', 'MessageDigest'),
        (r'CRC32', 'CRC32'),
        (r'createPackageContext', 'createPackageContext'),
        (r'ZipFile|ZipInputStream', '读 zip'),
    ],
    '证书固定': [
        (r'CertificatePinner', 'CertificatePinner'),
        (r'X509TrustManager|checkServerTrusted', 'TrustManager'),
        (r'setSSLSocketFactory|SSLSocketFactory', 'SSLSocketFactory'),
    ],
    '设备指纹': [
        (r'getDeviceId|getImei|getMeid', 'IMEI/MEID'),
        (r'ANDROID_ID|android_id', 'ANDROID_ID'),
        (r'getSerial|Build;->SERIAL', 'serial'),
        (r'oaid|OAID', 'OAID'),
        (r'getMacAddress|getHardwareAddress', 'MAC'),
    ],
    '原生加载': [
        (r'Ljava/lang/System;->loadLibrary', 'System.loadLibrary'),
        (r'getRunningProcesses|ActivityManager;->getRunning', '进程枚举'),
    ],
}

FOCUS_PREFIXES = ('com/ledreamer', 'com/legym', 'cn/legym', 'com/secneo',
                  'com/netease', 'io/dcloud')


def pkg_of(rel):
    parts = rel.replace('\\', '/').split('/')
    return '/'.join(parts[:-1]) if len(parts) > 1 else '(root)'


def main():
    hits = collections.defaultdict(lambda: collections.defaultdict(set))
    inner_total = file_total = 0
    inner_by_pkg = collections.Counter()

    for d in SMALI_DIRS:
        base = os.path.join(APKTOOL, d)
        for dirpath, _, files in os.walk(base):
            for fn in files:
                if not fn.endswith('.smali'):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, base)
                file_total += 1
                if '$' in fn:
                    inner_total += 1
                    inner_by_pkg[pkg_of(rel)] += 1
                try:
                    txt = open(full, 'r', encoding='utf-8', errors='replace').read()
                except Exception:
                    continue
                for cat, pats in PATTERNS.items():
                    for rx, label in pats:
                        if re.search(rx, txt):
                            hits[cat][rel].add(label)

    print('扫描: %d 个 smali, 内部类 %d 个' % (file_total, inner_total))
    print('\n%-12s %8s %10s' % ('类别', '全部', '自有/安全包'))
    for cat in PATTERNS:
        files = hits.get(cat, {})
        focus = [k for k in files if k.replace('\\', '/').startswith(FOCUS_PREFIXES)]
        print('%-12s %8d %10d' % (cat, len(files), len(focus)))

    out = {
        'file_total': file_total,
        'inner_total': inner_total,
        'inner_by_pkg': dict(inner_by_pkg.most_common(40)),
        'hits': {c: {f: sorted(v) for f, v in d.items()} for c, d in hits.items()},
    }
    dst = os.path.join(ROOT, 'report', 'anticheat-scan.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print('\n已写入', dst)


if __name__ == '__main__':
    main()
