# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

**single-context** —— 本仓库采用单上下文布局：全仓库共用**一份**根目录的 `GLOSSARY.md`，架构决策统一放在 `docs/adr/`。

- 不存在 `GLOSSARY-MAP.md`，也不存在按子项目拆分的 `GLOSSARY.md`
- 初始化时**没有**创建任何词汇表文件；留到第一次真正写下词条时由 `/domain-modeling` 懒创建

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root（single-context，全仓库共用这一份）
- **`docs/adr/`**: read ADRs that touch the area you're about to work in

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

```
/
├── GLOSSARY.md          ← 全仓库唯一一份
├── docs/
│   ├── adr/             ← 0001-*.md, 0002-*.md ...
│   └── agents/          ← 本目录（技能配置）
├── app/                 ← 桌面版
├── android/             ← 安卓版
└── tools/               ← 双端共用算法
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
