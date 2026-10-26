#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试：守住仓库结构、路径配置与补丁锚点。

用法:
    python scripts/tests/test_pipeline.py

不依赖 pytest，直接跑。返回 0 = 全绿。
"""
import json
import os
import subprocess
import sys

# Windows 控制台默认 GBK，输出里带替换字符会崩；统一切到 UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # scripts/tests -> 仓库根
sys.path.insert(0, os.path.join(ROOT, 'lib'))

FAIL = []


def check(name, cond, detail=''):
    print('  %-5s %s%s' % ('ok' if cond else 'FAIL', name,
                           ('  ' + detail) if detail else ''))
    if not cond:
        FAIL.append(name)


def main():
    print('仓库根: %s' % ROOT)

    # ---- 1. 共享算法 ----
    print('\n[1] lib/ 共享算法')
    try:
        import rules as R
        import run_sim as RS
        import route_gen as RG
        check('rules.point_in_fences', hasattr(R, 'point_in_fences'))
        check('run_sim.haversine', hasattr(RS, 'haversine'))
        check('route_gen._inset_loop', hasattr(RG, '_inset_loop'))
    except Exception as e:
        check('lib 导入', False, str(e))
        R = RS = RG = None

    # ---- 2. 围栏数据 ----
    print('\n[2] 围栏数据')
    fence_path = os.path.join(ROOT, 'mobile', 'assets', 'range_2024-2025_1.json')
    check('文件存在', os.path.isfile(fence_path), fence_path)
    poly = None
    if os.path.isfile(fence_path):
        with open(fence_path, encoding='utf-8') as f:
            d = json.load(f)
        poly = d['range']['rangeRunningRegion'][0]
        check('围栏点数 >= 3', len(poly) >= 3, '%d 点' % len(poly))

    # ---- 3. 关键文件 ----
    print('\n[3] 关键文件')
    required = [
        'mobile/build_mobile.sh',
        'mobile/patch_smali.py',
        'mobile/patch_assets.py',
        'mobile/vendor/apktool_3.0.3.jar',
        'mobile/hf-release.jks',
        'desktop/app.py',
        'desktop/config.py',
        'requirements.txt',
        'lib/rules.py',
        'lib/run_sim.py',
        'lib/route_gen.py',
        'lib/coord.py',
        'lib/legym_envelope.py',
        'scripts/build/gen_track_asset.py',
        '.github/workflows/android.yml',
        '.github/workflows/desktop.yml',
    ]
    for rel in required:
        check(rel, os.path.exists(os.path.join(ROOT, rel)))

    # ---- 4. 路径配置 ----
    print('\n[4] 路径配置')
    cfg = open(os.path.join(ROOT, 'desktop', 'config.py'), encoding='utf-8').read()
    check("desktop/config.py 的 TOOLS 指向 lib", "os.path.join(ROOT, 'lib')" in cfg)

    build_sh = open(os.path.join(ROOT, 'mobile', 'build_mobile.sh'), encoding='utf-8').read()
    check('build_mobile.sh 用 unpacked/apktool_out', 'unpacked/apktool_out' in build_sh)
    check('build_mobile.sh 用 vendor/apktool', 'vendor/apktool_3.0.3.jar' in build_sh)
    check('build_mobile.sh 产出到 dist/mobile', 'dist/mobile' in build_sh)

    for f in ('mobile/patch_assets.py', 'mobile/patch_smali.py'):
        src = open(os.path.join(ROOT, f), encoding='utf-8').read()
        check('%s 支持 APKTOOL_OUT' % f, 'APKTOOL_OUT' in src)

    gen = open(os.path.join(ROOT, 'scripts', 'build', 'gen_track_asset.py'),
               encoding='utf-8').read()
    check('gen_track_asset 用 ASSETS_OUT', 'ASSETS_OUT' in gen)

    # ---- 5. 补丁锚点 ----
    print('\n[5] 补丁锚点（--check）')
    apktool_out = os.path.join(ROOT, 'unpacked', 'apktool_out')
    if not os.path.isdir(apktool_out):
        print('  skip  没有解包树（unpacked/apktool_out 不存在），跳过锚点检查')
    else:
        env = dict(os.environ, APKTOOL_OUT=apktool_out)
        for script in ('mobile/patch_smali.py', 'mobile/patch_assets.py'):
            p = os.path.join(ROOT, script)
            r = subprocess.run([sys.executable, p, '--check'],
                               capture_output=True, text=True,
                               encoding='utf-8', errors='replace', env=env)
            last = (r.stdout or '').strip().splitlines()
            check('%s --check' % script, r.returncode == 0,
                  last[-1] if last else '')

    # ---- 6. 轨迹生成（端到端算法）----
    print('\n[6] 轨迹生成')
    if R and RS and RG and poly:
        fence = [[p['latitude'], p['longitude']] for p in poly]
        loop = RG._inset_loop(fence, 25.0, 50.0, 3.0, 10.0, 100.0)
        check('内缩环 >= 10 点', len(loop) >= 10, '%d 点' % len(loop))
        import math
        total = 0.0
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            total += RS.haversine(a[0], a[1], b[0], b[1])
        check('环周长 > 500m', total > 500, '%.0f m' % total)

        inside = sum(1 for la, lo in loop if R.point_in_fences(la, lo, [fence]))
        ratio = 100.0 * inside / len(loop)
        check('环顶点在围栏内 > 90%', ratio > 90, '%.1f%%' % ratio)

    print()
    if FAIL:
        print('失败 %d 项:' % len(FAIL))
        for f in FAIL:
            print('  - ' + f)
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
