# AGENTS.md

本文件给在本仓库工作的 AI agent 看。

## 仓库说明

乐健体育（`com.ledreamer.zz`）校园跑辅助工具，两个客户端共用 `lib/` 下的轨迹与规则算法：

- `desktop/` —— 桌面版 PyQt6 程序
- `mobile/` —— 手机版改包构建工程（`build_mobile.sh` 一键构建）
- `lib/` —— 双端共用算法（coord / rules / run_sim / route_gen / legym_envelope）
- `scripts/` —— 构建、运维、逆向、测试脚本
- `unpacked/` —— 解包树与原始 APK（已忽略，约 1GB）
- `dist/` —— 产物（已忽略）

结构改动后先跑 `python scripts/tests/test_pipeline.py` 验证路径与补丁锚点。

最终产物与 Release 在 GitHub 仓库 `Drayee/happyfuck`。

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues on `Drayee/happyfuck`, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, default label strings unchanged (`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

single-context —— one `GLOSSARY.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.
