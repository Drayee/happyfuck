#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出自有包/安全包的扫描命中（排除 R 资源类噪音）。

用法:
    python mobile/query_hits.py [前缀...]
默认前缀: com/ledreamer com/legym cn/legym com/secneo com/netease io/dcloud
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'report', 'anticheat-scan.json')
d = json.load(open(SRC, encoding='utf-8'))
hits = d['hits']

PREFIXES = tuple(sys.argv[1:]) or (
    'com/ledreamer', 'com/legym', 'cn/legym',
    'com/secneo', 'com/netease', 'io/dcloud')
SKIP_CATS = {'原生加载'}


def norm(f):
    return f.replace(chr(92), '/')


def noise(fn):
    base = fn.rsplit('/', 1)[-1]
    return ('R$' in base) or base == 'R.smali'


print('文件总数 %d / 内部类 %d' % (d['file_total'], d['inner_total']))
for cat, files in hits.items():
    if cat in SKIP_CATS:
        continue
    rows = [(norm(f), l) for f, l in files.items()
            if norm(f).startswith(PREFIXES) and not noise(norm(f))]
    if not rows:
        continue
    print('\n=== %s (%d) ===' % (cat, len(rows)))
    for fn, labels in sorted(rows):
        print('  %-82s %s' % (fn, ','.join(labels)))
