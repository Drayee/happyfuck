# HappyFuck 乐奸

乐健体育（`com.ledreamer.zz`）校园跑辅助工具，两个客户端 + 一套逆向研究资料。

| 目录 | 是什么 |
|---|---|
| `desktop/` | **桌面版** —— PyQt6 程序，地图画跑道、规则校验、定时提交 |
| `mobile/` | **手机版** —— 改包 APK 构建工程（Java 注入 + smali/so 补丁） |
| `unpacked/` | **解包文件** —— 原始 APK、apktool 树、jadx 树（全部忽略，不入库） |
| `lib/` | 双端共用算法（坐标系、规则、轨迹生成、AES 信封） |
| `scripts/` | **脚本** —— 构建 / 运维 / 逆向 / 测试 |
| `dist/` | **产物** —— APK、exe、日志（忽略） |
| `docs/` | 知识文档（`reverse/` 逆向资料、`agents/` 技能配置、`ci.md`） |

成品发布在 GitHub → [Drayee/happyfuck](https://github.com/Drayee/happyfuck/releases)

---

## 快速开始

### 手机版

```bash
# 首次：把原版 APK 放到 unpacked/QQbase.apk（或设 ORIG_APK 环境变量）
bash mobile/build_mobile.sh
# 产物：dist/mobile/happyfuck_mobile.apk
```

构建流程：

```
① apktool d  原版 APK        → unpacked/apktool_out/
② 生成轨迹资产              → apktool_out/assets/hf_route.txt
③ 打 JS 定位补丁            → uni-jsframework.js
④ 打 11 项 smali / so 补丁
⑤ apktool b
⑥ javac + d8 → classes7.dex 注入
⑦ apksigner 签名 v1+v2+v3   → dist/mobile/
```

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PYTHON` | 自动探测 | CI 上是 `python3` |
| `JAVA_HOME` | `C:/Program Files/Java/jdk-25` | 需 JDK 9+（用 `--release 8`） |
| `ANDROID_SDK` | `C:/Program Files (x86)/Android/android-sdk` | |
| `ORIG_APK` | `unpacked/QQbase.apk` | 没有解包树时用 |

### 桌面版

```bash
pip install -r requirements.txt
python desktop/app.py
```

打包：

```bash
pyinstaller --windowed --name HappyFuck --paths lib --paths desktop \
  --add-data "lib;lib" --add-data "desktop/assets;assets" desktop/app.py
```

### 测试

```bash
python scripts/tests/test_pipeline.py
```

校验：`lib/` 可导入、围栏数据、关键文件、路径配置、补丁锚点、轨迹生成。

---

## 目录细节

```
desktop/                  桌面版
  app.py                  入口
  map_panel.py            地图与画圈
  service.py              业务编排（登录/规则/生成/上传）
  scheduler.py            定时任务
  uploader.py             HTTP 上传
  config.py               路径与持久化（TOOLS → ../lib）
  data/                   运行时数据（忽略）

mobile/                   手机版构建工程
  build_mobile.sh         一键构建
  patch_smali.py          11 项 smali / so 补丁（幂等，带 --check）
  patch_assets.py         JS 定位补丁
  src/com/ledreamer/hf/   Java 注入代码（GPS / 编辑器 / 自动跑 / 日志）
  stub/                   高德 SDK 编译期替身（不进 dex）
  vendor/apktool_3.0.3.jar  必须与本地同版本（补丁是精确文本匹配）
  hf-release.jks          签名（口令 android，仅自用）
  assets/                 围栏数据（range_2024-2025_1.json）

lib/                      共用算法
  coord.py                坐标系转换
  rules.py                学校规则解析与围栏判定
  run_sim.py              轨迹生成（人类行为模型）
  route_gen.py            跑道几何（内缩环、重采样）
  legym_envelope.py       AES 信封

scripts/
  build/gen_track_asset.py  生成 hf_route / hf_track 资产
  ops/map_editor.py         画圈 GUI
  ops/go.py                 CLI 入口
  ops/logcat_hf.*           手机日志抓取
  ops/slim_apk.py           精简 APK（去 32 位 so）
  ops/run.bat               统一启动器
  reverse/                  反作弊扫描、证据脚本、Frida 脚本
  tests/test_pipeline.py    冒烟测试

unpacked/                 （忽略，约 1GB）
  QQbase.apk              原版 APK
  apktool_out/            apktool 反编译树
  jadx_out/               jadx 反编译

docs/
  ci.md                   CI 说明
  agents/                 技能套件配置（issue tracker / triage / domain）
  reverse/                逆向报告、审计、方案（shots/ 存截图）
  reverse/case/           案例记录（scope / timeline / workitems）
```

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/reverse/static-reverse-report.md](docs/reverse/static-reverse-report.md) | 静态逆向总报告 |
| [docs/reverse/anticheat-audit.md](docs/reverse/anticheat-audit.md) | 全量反作弊审计（31,797 smali / 14,509 内部类） |
| [docs/reverse/daily-auto-run-plan.md](docs/reverse/daily-auto-run-plan.md) | 每日自动跑实现方案 |
| [docs/reverse/audit-happyfuck-desktop.md](docs/reverse/audit-happyfuck-desktop.md) | 桌面版脚本审计 |
| [docs/ci.md](docs/ci.md) | CI 触发规则与排错 |
| [mobile/README.md](mobile/README.md) | 手机版详细文档（补丁清单、踩坑记录） |
| [desktop/README.md](desktop/README.md) | 桌面版详细文档 |

---

## 关键技术结论

**签名绑定有两套**

1. `libsecurity.so` 的 `checkSignature` —— 比对证书 DER 的 `Arrays.hashCode` 与 `0x8f977ed0`，已 `nop` 绕过
2. DexVMP 的 `Rengis.it()` —— 独立的 `getPackname`/`getSignature` 校验，重签名后恒 false，`hs()` 返回 null，已做空串回退

**客户端没有其他反作弊**

32k smali 扫完：无设备指纹上报、无 root/模拟器检测、无 mock 检测、无证书固定、易盾是死代码。剩下全是服务端校验（配速区间、围栏比例、时间窗）。

**轨迹噪声必须用 AR(1)**

独立噪声会让相邻采样点位移互相叠加 —— 设定 3.5 km 实测跑出 8.6 km，上报配速直接超区间。AR(1) 下 3.51 km / 449 s/km，与设定一致。

---

## 注意

- `mobile/hf-release.jks`（口令 `android`）是自用签名，**不要拿本仓库做公开分发**
- `unpacked/` 里的原版 APK 与反编译树都是第三方内容，仅供本机研究
- 仅供学习研究，使用风险自负
