#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 Java 里反射用到的字段名/方法名在 smali 里真实存在。

为什么需要这个：
    jadx 反编译出来的名字是**反混淆后的展示名**，不能直接用于反射。
    本项目已经因此踩过两次坑：
        LocationService.INSTANCE      -> 实际字段是 a
        getField("uploadRunInfoReqVo") -> 实际字段是 M
    两次都是"编译通过、运行时才炸"，靠人眼看代码抓不住。

检查策略：
    1) 精确检查 —— X = Class.forName("FQCN") 之后 X.getField("n")/X.getMethod("n")
       直接到该类的 smali 里核对。
    2) 动态检查 —— xxx.getClass().getField("n")
       Class 未知，退而在「App 自有类索引」里找这个名字是否存在。

用法:
    python scripts/tests/check_reflection_names.py
    python scripts/tests/check_reflection_names.py --verbose

返回 0 = 全部命中；1 = 有对不上的名字。
没有解包树时跳过（退出 0），方便在 CI 上跑。
"""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "mobile", "src")
APKTOOL = os.path.join(ROOT, "unpacked", "apktool_out")

# 动态反射时用来判定"这个名字存在"的类范围
APP_ROOTS = (
    "com/ledreamer",
    "com/legym",
    "cn/legym",
    "com/amap",
)

# 名字确实不在 smali 里、但运行时一定存在的（DexVMP 注入 / 系统类）
ALLOWLIST = {
    "hs": "DexVMP 运行时注入的 cn.legym.ai.util.Rengis.hs",
    "it": "DexVMP 运行时注入的 cn.legym.ai.util.Rengis.it",
}

# 整个类都不在 smali 里（运行时才注入），跳过对该类的精确校验
MISSING_OK = {
    "cn.legym.ai.util.Rengis": "DexVMP 在运行时注入，smali 里查不到",
}

FORNAME_RE = re.compile(
    r'Class\s*<\s*\??\s*>\s*(\w+)\s*=\s*Class\.forName\(\s*"([^"]+)"\s*\)')
SCOPED_RE = re.compile(r'\b(\w+)\.get(Field|Method)\(\s*"([^"]+)"')
DYN_RE = re.compile(r'\.getClass\(\)\.get(Field|Method)\(\s*"([^"]+)"')

FIELD_RE = re.compile(r'^\.field\s[^\n]*?\s([\w$]+):\S', re.M)
METHOD_RE = re.compile(r'^\.method\s[^\n]*?\s([\w$]+)\(', re.M)


def smali_dirs():
    if not os.path.isdir(APKTOOL):
        return []
    return [os.path.join(APKTOOL, d) for d in sorted(os.listdir(APKTOOL))
            if d.startswith("smali") and os.path.isdir(os.path.join(APKTOOL, d))]


def read(p):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def names_of_class(fqcn, dirs):
    """返回 (fields, methods)，找不到类时返回 None。"""
    rel = fqcn.replace(".", "/") + ".smali"
    for d in dirs:
        p = os.path.join(d, rel)
        if os.path.isfile(p):
            t = read(p)
            return set(FIELD_RE.findall(t)), set(METHOD_RE.findall(t))
    return None


def build_app_index(dirs):
    """扫 App 自有类，收集所有字段名与方法名。"""
    fields, methods = set(), set()
    for d in dirs:
        for root_name in APP_ROOTS:
            base = os.path.join(d, root_name.replace("/", os.sep))
            if not os.path.isdir(base):
                continue
            for dirpath, _, files in os.walk(base):
                for fn in files:
                    if not fn.endswith(".smali"):
                        continue
                    try:
                        t = read(os.path.join(dirpath, fn))
                    except Exception:
                        continue
                    fields.update(FIELD_RE.findall(t))
                    methods.update(METHOD_RE.findall(t))
    return fields, methods


def java_files():
    for dirpath, _, files in os.walk(SRC):
        for fn in files:
            if fn.endswith(".java"):
                yield os.path.join(dirpath, fn)


def main():
    verbose = "--verbose" in sys.argv
    dirs = smali_dirs()
    if not dirs:
        print("[skip] 没有解包树 %s" % APKTOOL)
        print("       先 bash mobile/build_mobile.sh 生成，或 apktool d 原始 APK")
        return 0

    print("解包树: %d 个 smali 目录" % len(dirs))
    print("App 索引: 扫描中…", end="")
    app_fields, app_methods = build_app_index(dirs)
    print(" %d 字段 / %d 方法" % (len(app_fields), len(app_methods)))
    print()

    problems = []
    checked = 0

    for path in sorted(java_files()):
        text = read(path)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")

        # --- 1) 精确检查 ---
        varmap = {m.group(1): m.group(2) for m in FORNAME_RE.finditer(text)}
        for vm in SCOPED_RE.finditer(text):
            var, kind, name = vm.group(1), vm.group(2), vm.group(3)
            if var not in varmap:
                continue
            fqcn = varmap[var]
            if fqcn in MISSING_OK:
                if verbose:
                    print("  skip %s  %s（%s）" % (rel, fqcn, MISSING_OK[fqcn]))
                continue
            got = names_of_class(fqcn, dirs)
            checked += 1
            if got is None:
                problems.append("%s: 找不到类 %s（源文件里 %s.get%s(\"%s\")）"
                                % (rel, fqcn, var, kind, name))
                continue
            fields, methods = got
            pool = fields if kind == "Field" else methods
            if name not in pool:
                hint = ""
                if kind == "Field":
                    hint = "  该类 public 字段: " + ", ".join(sorted(fields)[:12])
                problems.append("%s: %s 里没有 %s %s%s"
                                % (rel, fqcn.split(".")[-1], 
                                   "字段" if kind == "Field" else "方法", name, hint))
            elif verbose:
                print("  ok  %s  %s.%s" % (rel, fqcn.split(".")[-1], name))

        # --- 2) 动态检查 ---
        for dm in DYN_RE.finditer(text):
            kind, name = dm.group(1), dm.group(2)
            if name in ALLOWLIST:
                continue
            checked += 1
            pool = app_fields if kind == "Field" else app_methods
            if name not in pool:
                problems.append("%s: 动态反射 %s \"%s\" 在 App 自有类里找不到"
                                % (rel, "字段" if kind == "Field" else "方法", name))
            elif verbose:
                print("  ok  %s  *.%s" % (rel, name))

    print()
    print("检查了 %d 个反射名字" % checked)
    if problems:
        print("对不上 %d 处：" % len(problems))
        for p in problems:
            print("  FAIL  " + p)
        print()
        print("提示：以 unpacked/apktool_out/smali* 为准；jadx 里的名字不可用于反射。")
        return 1
    print("全部命中")
    return 0


if __name__ == "__main__":
    sys.exit(main())
