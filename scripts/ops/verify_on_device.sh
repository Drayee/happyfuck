#!/usr/bin/env bash
# 真机验证：装包 -> 拉日志 -> 等到关键行出现 -> 给红/绿
#
# 为什么需要它：这个项目连续 5 个 bug 都是"编译通过 + CI 绿"就发版，
# 直到真机才暴露。CI 只能证明"能打包"，不能证明"跑得通"。
#
# 用法:
#   bash scripts/ops/verify_on_device.sh                  # 默认 APK
#   bash scripts/ops/verify_on_device.sh -a path/to.apk
#   bash scripts/ops/verify_on_device.sh -t 2400         # 超时秒数（默认 40 分钟）
#   bash scripts/ops/verify_on_device.sh --watch-only     # 只盯日志，不装包
#
# 判定:
#   绿 = 日志里出现 "uploadVo = built"
#   红 = 出现 "uploadVo = NULL" / "S() invoked" 之后仍无 VO / 超时
set -uo pipefail

APK_DEFAULT="$(cd "$(dirname "$0")/../.." && pwd)/dist/mobile/happyfuck_mobile.apk"
APK="$APK_DEFAULT"
TIMEOUT=2400
WATCH_ONLY=0
PKG="com.ledreamer.zz"
LOG="/sdcard/Android/data/${PKG}/files/hf_log.txt"

while [ $# -gt 0 ]; do
  case "$1" in
    -a|--apk) APK="$2"; shift 2 ;;
    -t|--timeout) TIMEOUT="$2"; shift 2 ;;
    --watch-only) WATCH_ONLY=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

# ---------- adb 探测 ----------
ADB=""
for c in \
  "${ANDROID_SDK:-C:/Program Files (x86)/Android/android-sdk}/platform-tools/adb.exe" \
  "C:/Program Files/BlueStacks_nxt_cn/HD-Adb.exe" \
  "$(command -v adb 2>/dev/null)"; do
  if [ -n "$c" ] && [ -x "$c" ]; then ADB="$c"; break; fi
done
if [ -z "$ADB" ]; then echo "[!] 找不到 adb，设置 ADB=/path/to/adb"; exit 1; fi
D=()
if ! "$ADB" devices 2>/dev/null | awk 'NR>1 && $2=="device"{f=1} END{exit !f}'; then
  echo "[!] 没有设备。手机连数据线 + 打开 USB 调试"
  "$ADB" devices
  exit 1
fi
DEV=$("$ADB" devices | awk 'NR>1 && $2=="device"{print $1; exit}')
D=(-s "$DEV")
echo "[i] adb    : $ADB"
echo "[i] device : $DEV"

# ---------- 装包 ----------
if [ "$WATCH_ONLY" -eq 0 ]; then
  [ -f "$APK" ] || { echo "[!] 找不到 APK: $APK"; exit 1; }
  echo "[i] 安装 $APK"
  "$ADB" "${D[@]}" install -r -t "$APK" | tail -1
  echo "[i] 清空旧日志"
  "$ADB" "${D[@]}" shell "rm -f $LOG" 2>/dev/null
  "$ADB" "${D[@]}" logcat -c 2>/dev/null
  echo "[i] 启动 App"
  "$ADB" "${D[@]}" shell am force-stop "$PKG" 2>/dev/null
  sleep 2
  "$ADB" "${D[@]}" shell am start -n "$PKG/.activity.splash.SplashActivity" >/dev/null 2>&1
fi

# ---------- 日志可读性 ----------
if ! "$ADB" "${D[@]}" shell "test -f $LOG" 2>/dev/null; then
  echo "[!] 读不到 $LOG"
  echo "    部分 ROM 不允许 adb 读 Android/data。请在手机上："
  echo "    长按图标 -> 运行日志，手动查看。"
  exit 1
fi

echo
echo "=================================================================="
echo " 现在在手机上操作："
echo "   长按图标 -> 设计跑步轨迹 -> 底部「自动」-> 「立即试跑」"
echo "   （首次必须先手动跑过一次，才有缓存的规则参数）"
echo
echo " 脚本会一直盯日志，直到出现结论或超时（${TIMEOUT}s）"
echo "=================================================================="
echo

# ---------- 轮询 ----------
seen_start=0 seen_finish=0
deadline=$(( $(date +%s) + TIMEOUT ))
last_print=0

while [ "$(date +%s)" -lt "$deadline" ]; do
  TAIL=$("$ADB" "${D[@]}" shell "tail -n 400 $LOG" 2>/dev/null | tr -d '\r')

  if [ -z "$TAIL" ]; then
    sleep 5; continue
  fi

  if [ "$seen_start" -eq 0 ] && echo "$TAIL" | grep -q "HF_AUTO: startRun ok"; then
    seen_start=1; echo "[i] 已开跑"
  fi
  if [ "$seen_finish" -eq 0 ] && echo "$TAIL" | grep -q "HF_AUTO: S() invoked"; then
    seen_finish=1; echo "[i] 已触发收尾"
  fi

  if echo "$TAIL" | grep -q "uploadVo = built"; then
    echo
    echo "=================================================================="
    echo " ✅ PASS：上传数据已构建（uploadVo = built）"
    echo "=================================================================="
    echo "$TAIL" | grep -E "HF_AUTO|HF_LOAD|HF_DRV" | tail -12
    exit 0
  fi

  if echo "$TAIL" | grep -q "uploadVo = NULL"; then
    echo
    echo "=================================================================="
    echo " ❌ FAIL：收尾跑了，但上传数据没构建（uploadVo = NULL）"
    echo "=================================================================="
    echo "$TAIL" | grep -E "HF_AUTO|HF_LOAD|HF_DRV|HF_ERROR" | tail -20
    exit 1
  fi

  # 每 60 秒打一行进度，别刷屏
  now=$(date +%s)
  if [ $(( now - last_print )) -ge 60 ]; then
    last_print=$now
    left=$(( deadline - now ))
    echo "[i] 等待中… 剩余 ${left}s  $(echo "$TAIL" | tail -1)"
  fi

  sleep 10
done

echo
echo "=================================================================="
echo " ⏱ 超时（${TIMEOUT}s）未得到结论"
echo "=================================================================="
"$ADB" "${D[@]}" shell "tail -n 40 $LOG" 2>/dev/null | tr -d '\r'
echo
if [ "$seen_start" -eq 0 ]; then
  echo "提示：一直没开跑。检查"
  echo "  - 是否已经手动跑过一次（有缓存的规则参数）"
  echo "  - 自动跑设置里是否已经保存过时间/模式"
  echo "  - 日志里有没有 HF_AUTO: 开头的行"
elif [ "$seen_finish" -eq 0 ]; then
  echo "提示：开跑了但没收尾。检查"
  echo "  - 目标距离是否比实际跑的多（HF_AUTO: target reached 没出现？）"
  echo "  - LocationService 是否在跑（HF_DRV: tick 是否还在刷）"
else
  echo "提示：收尾了但没结论，把上面日志末尾发出来"
fi
exit 1
