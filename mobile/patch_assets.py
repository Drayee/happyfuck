#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HappyFuck 手机版 —— 资产层补丁（可重复执行）。

只处理 apktool_out/assets/ 下的资源文件，不改 smali。

当前补丁：
  1. uni-jsframework.js 的 getLocation()
     直接以合成 GCJ-02 坐标回调，绕过 AMap 真实定位，
     解决「点击范围跑提示获取定位失败」。

用法：
    python mobile/patch_assets.py            # 应用补丁
    python mobile/patch_assets.py --check    # 只检查是否已应用
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(ROOT, 'apktool_out', 'assets', 'uni-jsframework.js')

# 合成坐标：四川农业大学雅安校区围栏内，GCJ-02
LAT = '29.9821616'
LON = '102.986433'

ANCHOR = ('getLocation:function(e,t){void 0===e&&(e={});var n=e.type;'
          'void 0===n&&(n="wgs84");')

INJECT = ('oi(t,{type:n,altitude:0,latitude:%s,longitude:%s,'
          'speed:2.222,accuracy:5,address:null,errMsg:"getLocation:ok"});return;'
          % (LAT, LON))


def main():
    check_only = '--check' in sys.argv
    if not os.path.exists(JS):
        print('[skip] 找不到 %s（先执行 apktool d）' % JS)
        return 0

    with open(JS, 'r', encoding='utf-8', errors='replace') as f:
        s = f.read()

    if INJECT in s:
        print('[ok] uni-jsframework.js 已打过定位补丁')
        return 0

    cnt = s.count(ANCHOR)
    if cnt != 1:
        print('[fail] 锚点匹配 %d 次（期望 1 次），JS 结构可能已变' % cnt)
        return 1

    if check_only:
        print('[todo] 定位补丁尚未应用')
        return 1

    s = s.replace(ANCHOR, ANCHOR + INJECT, 1)
    with open(JS, 'w', encoding='utf-8', newline='') as f:
        f.write(s)

    print('[ok] 已给 uni-jsframework.js 打上定位补丁')
    print('     getLocation() 将直接返回 GCJ-02 (%s, %s)' % (LAT, LON))
    return 0


if __name__ == '__main__':
    sys.exit(main())
