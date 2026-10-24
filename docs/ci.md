# CI 说明

两个产物、两条独立流水线：

| 代号 | 产物 | Workflow | 触发 |
|---|---|---|---|
| **w** | Windows 桌面版 `HappyFuck-v*-windows-x64.exe` | `.github/workflows/ci.yml` | 桌面代码改动 / `v*` tag |
| **a** | 安卓改包 `happyfuck_mobile.apk` | `.github/workflows/android.yml` | `android/**` 改动 / `android-*`、`v*` tag |

---

## 1. 怎么触发

### 1.1 路径过滤（默认）

| 改动 | 跑哪条 |
|---|---|
| `app/**`、`tools/**`、`happyfuck.spec` | **w** |
| `android/**` | **a** |
| 两边都改 | 两条都跑 |

### 1.2 提交前缀（强制）

提交信息**第一行**：

```bash
git commit -m "a: 修安卓权限门禁"      # 只跑 a
git commit -m "w: 修托盘图标"          # 只跑 w
git commit -m "docs: 改文档"            # 按路径判断
```

`a:` / `A:` / `[a]` → 强制跑安卓；`w:` / `W:` / `[w]` → 跳过安卓。

### 1.3 手动 / 发版

- **Actions → Android APK → Run workflow**，可勾 `release`
- **打 tag**：`android-v1.0.2` 或 `v1.0.2` → 自动构建并发 Release

---

## 2. 安卓流水线做了什么

```
ubuntu-latest
 ├ JDK 17
 ├ 预装 Android SDK（不用 setup-android，它会去装已下线的 tools 包）
 │    缺 build-tools;35.0.0 / platforms;android-34 时用 sdkmanager 补
 ├ python 3.12
 ├ 从 Release `ci-assets` 下载原版 APK（112MB，不入库）
 │    私有仓库资产直链要鉴权，所以用 gh release download 而不是 curl
 ├ 校验 android/tools/apktool_3.0.3.jar 存在
 └ bash android/mobile/build_mobile.sh
      ① apktool d 原版 APK            （首次，约 18s）
      ② 生成轨迹资产 hf_route/hf_track
      ③ 打 JS 定位补丁
      ④ 打 11 项 smali / so 补丁
      ⑤ apktool b
      ⑥ javac + d8 → classes7.dex 注入
      ⑦ apksigner 签名 v1+v2+v3
```

单次耗时约 **2 分钟**（含反编译）。

### 2.1 原版 APK 放在哪

Release **`ci-assets`** 里，资产名 `QQbase.1.apk`。

**不要删这个 Release**，删了安卓 CI 直接失败。
换新版本原版包：往这个 Release 传新的 `.apk`，`gh release download --pattern '*.apk'` 会取到最新的匹配项（如果同时存在多个 `.apk` 请先删旧的）。

### 2.2 为什么把 15MB 的 apktool jar 入库

`android/mobile/patch_smali.py` 是**精确文本匹配**：

```python
""".method public final initData()V
    .locals 2

    .line 1
    invoke-virtual {p0}, Landroid/app/Activity;->getIntent()Landroid/content/Intent;"""
```

apktool 换版本 → 反编译出的 smali 可能连寄存器命名、注释行都变 → 锚点匹配失败 →
补丁被**静默跳过** → 构建成功但功能全废。这是最难查的失败模式，所以版本必须锁死。

---

## 3. 产物

```
Actions → 某次运行 → 页面底部 Artifacts
  happyfuck-android-apk  →  happyfuck_mobile.apk + .idsig
```

打 tag 时会额外创建 Release：

| tag | Release |
|---|---|
| `android-v*` | 挂 `happyfuck_mobile.apk` |
| `v*` | 挂 `HappyFuck-v*-windows-x64.exe`（桌面） |

---

## 4. 本地构建

```bash
# 安卓（需要 ORIG_APK 指向原版包，apktool_out 不存在时会自动反编译）
cd android
ORIG_APK=/path/to/QQbase.apk bash mobile/build_mobile.sh

# 桌面
pip install -r requirements.txt
pyinstaller happyfuck.spec
```

`build_mobile.sh` 的环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PYTHON` | 自动探测 | CI 上是 `python3` |
| `JAVA_HOME` | `C:/Program Files/Java/jdk-25` | 需要 JDK 9+（用 `--release 8`） |
| `ANDROID_SDK` | `C:/Program Files (x86)/Android/android-sdk` | |
| `ORIG_APK` | 无 | `apktool_out` 不存在时必需 |

---

## 5. 已知问题

| 问题 | 说明 |
|---|---|
| 本机 `git push` 连不上 github.com:443 | 但 `gh api` 正常。可用 Git Data API 直接推提交（blobs → tree → commit → 更新 ref） |
| `android-actions/setup-android@v3` 报 `Failed to find package 'tools'` | 该包已下线。用预装 SDK + `sdkmanager` 补包 |
| 私有仓库 Release 直链需鉴权 | CI 里用 `gh release download`，不要用 `curl` |
| `hf-release.jks` 在仓库里 | 口令 `android`，仅自用；要公开发布请换成 Secrets 里的 keystore |
