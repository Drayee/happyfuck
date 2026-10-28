#!/usr/bin/env bash
# 安装仓库的 git hooks（hook 文件本身不入库，靠这个脚本复现）
#
# 用法: bash scripts/ops/install_git_hooks.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
HOOK_DIR="$(git rev-parse --git-dir)/hooks"
mkdir -p "$HOOK_DIR"

cat > "$HOOK_DIR/pre-commit" <<'HOOK'
#!/usr/bin/env bash
# 由 scripts/ops/install_git_hooks.sh 生成
set -e
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3 python "C:/Program Files/Python313/python.exe"; do
    command -v "$c" >/dev/null 2>&1 && PY="$c" && break
  done
fi
[ -n "$PY" ] || { echo "[pre-commit] 找不到 python，跳过检查"; exit 0; }

fail=0
echo "[pre-commit] 1/3 反射名字（jadx 名不可用于反射）"
"$PY" scripts/tests/check_reflection_names.py || fail=1

echo "[pre-commit] 2/3 仓库结构 + 轨迹生成"
"$PY" scripts/tests/test_pipeline.py > /tmp/hf_test_pipeline.log 2>&1 || {
  tail -20 /tmp/hf_test_pipeline.log
  fail=1
}

echo "[pre-commit] 3/3 shell 语法"
for f in mobile/build_mobile.sh scripts/ops/*.sh; do
  [ -f "$f" ] || continue
  bash -n "$f" || { echo "  语法错误: $f"; fail=1; }
done

if [ "$fail" -ne 0 ]; then
  echo
  echo "[pre-commit] ❌ 检查未通过，提交已中止。"
  echo "             确认是有意为之可加 --no-verify 跳过。"
  exit 1
fi
echo "[pre-commit] ✅ 全部通过"
HOOK

chmod +x "$HOOK_DIR/pre-commit"
echo "已安装: $HOOK_DIR/pre-commit"
echo
echo "验证一下："
bash "$HOOK_DIR/pre-commit"
