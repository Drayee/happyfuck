# CI 说明

本仓库有两条独立流水线，按**路径**和**提交前缀**区分：

| 代号 | 产物 | Workflow | 触发路径 |
|---|---|---|---|
| **w** | `HappyFuck-win64.zip` | `.github/workflows/desktop.yml` | `desktop/**`、`lib/**`、`requirements.txt` |
| **a** | `happyfuck_mobile.apk` | `.github/workflows/android.yml` | `mobile/**`、`lib/**`、`scripts/build/**` |

## 触发方式

### 路径过滤（默认）

改了哪个目录跑哪条；改 `lib/**` 两条都跑。

### 提交前缀（强制）

提交信息**第一行**：

```bash
git commit -m "a: 修安卓权限门禁"    # 只跑 a
git commit -m "w: 修托盘图标"        # 只跑 w
git commit -m "a,w: 两边都改了"      # 都跑
git commit -m "docs: 改文档"         # 按路径判断
```

规则：`a:` / `A:` / `[a]` → 跑安卓；`w:` / `W:` / `[w]` → 跳过安卓（桌面反之）。

前缀解析放在独立的 `gate` job 里，`build` 通过 `needs.gate.outputs.run` 决定跑不跑——
比写在 `if:` 表达式里好调试，日志里能直接看到它解析出的第一行提交信息。

### 手动 / 发版

- **Actions → 选 workflow → Run workflow**（可勾 `release`）
- **打 tag**：`android-v1.0.2` / `desktop-v1.0.2` / `v1.0.2` → 自动构建并发 Release

## 安卓流水线做了什么

```
ubuntu-latest
 ├ JDK 17（temurin）
 ├ 预装 Android SDK（不用 setup-android，它会去装已下线的 tools 包）
 │   缺 build-tools;35.0.0 / platforms;android-34 时用 sdkmanager 补
 ├ python 3.12
 ├ 从 Release `ci-assets` 下载原版 APK → unpacked/QQbase.apk
 │   私有仓库资产直链要鉴权，所以用 gh release download 而不是 curl
 ├ 校验 mobile/vendor/apktool_3.0.3.jar 存在
 └ bash mobile/build_mobile.sh
      ① apktool d 原版 APK            → unpacked/apktool_out/
      ② 生成轨迹资产 hf_route / hf_track
      ③ 打 JS 定位补丁
      ④ 打 11 项 smali / so 补丁
      ⑤ apktool b
      ⑥ javac + d8 → classes7.dex 注入
      ⑦ apksigner 签名 v1+v2+v3
```

单次约 **2 分钟**（含反编译）。

### 原版 APK 放在哪

Release **`ci-assets`** 里（资产名 `QQbase.1.apk`）。**不要删这个 Release**，
删了安卓 CI 直接失败。

### 为什么把 15MB 的 apktool jar 入库

`mobile/patch_smali.py` 是**精确文本匹配**：

```python
""".method public final initData()V
    .locals 2

    .line 1
    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;"""
```

apktool 换版本 → 反编译出的 smali 可能连寄存器命名、注释行都变 → 锚点匹配失败 →
补丁被**静默跳过** → 构建成功但功能全废。所以版本必须锁死在 `mobile/vendor/`。

## 产物

```
Actions → 某次运行 → 页面底部 Artifacts
  happyfuck-android-apk  →  happyfuck_mobile.apk + .idsig
  happyfuck-windows      →  HappyFuck-win64.zip
```

打 tag 时额外创建 Release。

## 本地构建

```bash
# 安卓（unpacked/QQbase.apk 存在就不用设 ORIG_APK）
bash mobile/build_mobile.sh

# 桌面
pip install -r requirements.txt
pyinstaller --windowed --name HappyFuck --paths lib --paths desktop \
  --add-data "lib;lib" --add-data "desktop/assets;assets" desktop/app.py

# 冒烟测试（结构改动后必跑）
python scripts/tests/test_pipeline.py
```

## 与 GitHub 仓库的布局差异

发布用的 GitHub 仓库 `Drayee/happyfuck` 采用 **`app/` + `android/` + `tools/`** 布局
（它的 `ci.yml` / `android.yml` 按那套路径写）。本仓库重构为
`desktop/` + `mobile/` + `lib/` + `scripts/` 之后，两边路径不再一一对应，
同步内容文件时不要覆盖对方的 `.github/`。

## 已知问题

| 问题 | 说明 |
|---|---|
| 本机 `git push` 连不上 `github.com:443` | 但 `gh api` 正常，可用 Git Data API 推提交（blobs → tree → commit → 更新 ref） |
| `android-actions/setup-android@v3` 报 `Failed to find package 'tools'` | 该包已下线，用预装 SDK + `sdkmanager` 补包 |
| 私有仓库 Release 直链需鉴权 | CI 里用 `gh release download`，不要用 `curl` |
| `mobile/hf-release.jks` 在仓库里 | 口令 `android`，仅自用；要公开发布请换 Secrets 里的 keystore |
