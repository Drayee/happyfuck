#!/usr/bin/env bash
# HappyFuck 手机版 —— 一键构建脚本
#
# 产出: mobile/dist/happyfuck_<version>.apk
# 依赖: JDK 17+ / Android SDK build-tools (apksigner, d8) / Python 3 / apktool_3.0.3.jar
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ---- Python 探测（CI 上是 python3，本机是完整路径）----
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in "C:/Program Files/Python313/python.exe" python3 python; do
    if [ -x "$c" ] || command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then echo "找不到 python，设置 PYTHON=/path/to/python"; exit 1; fi
echo "==> python: $PY"

JAVA_HOME="${JAVA_HOME:-C:/Program Files/Java/jdk-25}"
JAVA="$JAVA_HOME/bin/java"
JAVAC="$JAVA_HOME/bin/javac"
SDK="${ANDROID_SDK:-C:/Program Files (x86)/Android/android-sdk}"
ANDROID_JAR="$SDK/platforms/android-34/android.jar"
D8_JAR="$SDK/build-tools/35.0.0/lib/d8.jar"
APKSIGNER="$SDK/build-tools/35.0.0/apksigner"
[ -x "$APKSIGNER" ] || APKSIGNER="$SDK/build-tools/35.0.0/apksigner.bat"   # Windows
APKTOOL_JAR="$ROOT/tools/apktool_3.0.3.jar"
KEYSTORE="${HF_KEYSTORE:-$ROOT/mobile/hf-release.jks}"
KS_PASS="${HF_KS_PASS:-android}"
KS_ALIAS="${HF_KS_ALIAS:-hf}"

DIST="$ROOT/mobile/dist"
BUILD="$ROOT/mobile/build"
mkdir -p "$DIST" "$BUILD"

if [ ! -d apktool_out ]; then
  if [ -z "${ORIG_APK:-}" ] || [ ! -f "${ORIG_APK:-}" ]; then
    echo "[!] apktool_out 不存在，且未设置 ORIG_APK=/path/to/QQbase.apk"
    exit 1
  fi
  echo "==> [1.9/6] 反编译原始 APK（首次）"
  "$JAVA" -Xmx4g -jar "$APKTOOL_JAR" d "$ORIG_APK" -o apktool_out -f
fi

echo "==> [1/6] 生成范围跑轨迹资产"
"$PY" tools/gen_track_asset.py

echo "==> [1.5/6] 资产层补丁（uni-jsframework.js 定位）"
"$PY" mobile/patch_assets.py

echo "==> [1.8/6] smali / so 层补丁（幂等）"
"$PY" mobile/patch_smali.py

echo "==> [2/6] apktool 重打包（含 smali 补丁）"
"$JAVA" -Xmx4g -jar "$APKTOOL_JAR" b apktool_out -o "$BUILD/base_unsigned.apk"

echo "==> [3/6] 编译 -> dex（stub 与业务码一起编译，stub 不进 dex）"
rm -rf "$BUILD/classes" "$BUILD/dex"
mkdir -p "$BUILD/classes" "$BUILD/dex"

# 必须显式列出所有源文件：
# Windows 版 javac 的 -sourcepath / -cp 分隔符是 ';'，而 MSYS 会把含 ':'
# 的整串当成一个路径，导致 stub 目录解析不到。
"$JAVAC" --release 8 -cp "$ANDROID_JAR" -d "$BUILD/classes" \
  $(find mobile/src mobile/stub -name "*.java" | tr '\n' ' ') \
  2>&1 | grep -vE "警告|warning|已过时|源值|目标值|Xlint" || true

# stub 只用于编译；真实类在 APK 的 dex 里，d8 只需保留引用
rm -rf "$BUILD/classes/com/amap"

"$JAVA" -Xmx2g -cp "$D8_JAR" com.android.tools.r8.D8 --release \
  --lib "$ANDROID_JAR" --output "$BUILD/dex" --classpath "$ANDROID_JAR" \
  $(find "$BUILD/classes" -name "*.class" | tr '\n' ' ')

echo "==> [4/6] 注入 classes7.dex"
"$PY" - "$BUILD" <<'PY'
import zipfile, shutil, os, sys
build = sys.argv[1]
src = os.path.join(build, 'base_unsigned.apk')
out = os.path.join(build, 'hf_unsigned.apk')
shutil.copy2(src, out)
with zipfile.ZipFile(out, 'a', zipfile.ZIP_DEFLATED) as zf:
    zf.write(os.path.join(build, 'dex', 'classes.dex'), 'classes7.dex')
print('   injected ->', out, os.path.getsize(out), 'bytes')
PY

echo "==> [5/6] 签名"
"$APKSIGNER" sign --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" \
  --key-pass "pass:$KS_PASS" --ks-key-alias "$KS_ALIAS" \
  --v1-signing-enabled true --v2-signing-enabled true \
  --out "$DIST/happyfuck_mobile.apk" "$BUILD/hf_unsigned.apk" 2>&1 | grep -v WARNING || true

echo "==> [6/6] 校验"
"$APKSIGNER" verify --verbose "$DIST/happyfuck_mobile.apk" 2>&1 | head -4

echo ""
echo "完成: $DIST/happyfuck_mobile.apk"
ls -la "$DIST/happyfuck_mobile.apk"
