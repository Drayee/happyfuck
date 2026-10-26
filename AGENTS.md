# AGENTS.md

本文件给在本仓库工作的 AI agent 看。

## 仓库说明

乐健体育（`com.ledreamer.zz`）校园跑辅助工具，两个客户端共用 `tools/` 下的轨迹与规则算法：

- `app/` —— 桌面版 PyQt6 程序
- `android/` —— 安卓改包构建工程（在本地工作区位于 `work/qqbase-apk/`）

最终产物与 Release 在 GitHub 仓库 `Drayee/happyfuck`。

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues on `Drayee/happyfuck`, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, default label strings unchanged (`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

single-context —— one `GLOSSARY.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.
