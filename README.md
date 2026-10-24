# HappyFuck 乐奸

校园跑（乐健体育 `com.ledreamer.zz`）辅助工具，两个客户端：

| 客户端 | 形态 | 适合场景 |
|---|---|---|
| **桌面版** | PyQt6 Windows 程序 | 在电脑上画跑道、看规则、定时提交 |
| **安卓版** | 改包 APK | 手机上直接跑，不用电脑、不用 root |

两者共用同一套轨迹几何与规则校验算法（`tools/`）。

---

## 下载

| 版本 | 地址 |
|---|---|
| 桌面版（Windows x64） | [最新 Release](https://github.com/Drayee/happyfuck/releases/latest) |
| 安卓版（APK） | [android-v1.0.1](https://github.com/Drayee/happyfuck/releases/tag/android-v1.0.1) |

---

## 安卓版

基于原版 3.10.3 重打包，走 App 自己的定位 → 计距 → 围栏 → 打卡 → 上传链路，
不伪造任何接口调用。

### 功能

- **范围跑一键刷** —— 合成 GPS 注入 `onLocationChanged`，App 自己算里程和配速
- **手动画轨迹** —— 长按图标进编辑器，地图上点圈，保存即生效（应用内持久化）
- **围栏显示** —— 跑过一次后自动缓存学校围栏，编辑器里红色虚线标出
- **每日自动跑** —— 半自动（到点通知）/ 全自动（到点直接开跑），设置里可切换
- **运行日志** —— 应用内直接查看，不需要 adb 或电脑

### 安装

1. 下载 `happyfuck_mobile.apk`
2. 允许「安装未知来源应用」后安装
3. 长按桌面图标，出现两个入口：

```
设计跑步轨迹     画圈、设时间、看日志
运行日志         直接看执行记录
```

### 首次使用

> **必须先手动跑一次范围跑。**

第一次运行会把学期规则（`serRuleCondition`）和用户信息序列化缓存下来，
之后「每日自动跑」才有东西回放。没跑过就点自动跑，会提示「还没有基准参数」。

### 权限

| 权限 | 什么时候需要 |
|---|---|
| 闹钟和提醒（Android 12+） | 用「每日自动跑」时 |
| 悬浮窗 / 后台弹出界面 | 用**全自动**模式时（半自动不需要） |
| 通知（Android 13+） | 半自动模式 |

国产 ROM 建议额外设置：自启动白名单、电池优化无限制、多任务界面加锁。
不做这几项，典型症状是「昨天跑了今天没跑」。

### 换学校 / 换围栏

不用重装，把新的 `hf_route.txt` 推到：

```
/sdcard/Android/data/com.ledreamer.zz/files/hf_route.txt
```

文件格式：

```
# 注释行
pace=450          # 秒/公里
noise=0.9         # GPS 噪声标准差（米）
cadence=172       # 步/分钟
29.9821874,102.9864419   # 关键点，闭环，至少 3 个
29.9817397,102.9864325
```

运行时沿折线按配速插值，再叠加 AR(1) 时间相关噪声，每次跑的坐标都不同。

---

## 桌面版

在真实高德地图上画跑道，按学校规则生成符合人类跑步特征的轨迹，定时自动提交。

### 运行

```bash
pip install -r requirements.txt
python app/app.py            # 或 python app/app.py --debug
```

### 打包

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean happyfuck.spec
# 产物：dist/HappyFuck.exe
```

详细说明见 [`app/README.md`](app/README.md)。

---

## 目录结构

```
app/                 桌面版 PyQt6 主程序
  app.py             入口
  map_panel.py       地图与画圈
  service.py         业务编排（登录/规则/生成/上传）
  scheduler.py       定时任务
  uploader.py        HTTP 上传
tools/               共用核心
  coord.py           坐标系转换
  rules.py           学校规则解析与围栏判定
  run_sim.py         轨迹生成（人类行为模型）
  legym_envelope.py  AES 信封
android/             安卓版构建工程
  mobile/            构建脚本 + Java 注入代码 + 高德 stub
  tools/             gen_track_asset.py / route_gen.py / apktool jar
  assets/            学校围栏数据
docs/ci.md           CI 说明
happyfuck.spec       桌面版 PyInstaller 配置
```

---

## CI

两条独立流水线，靠**路径**和**提交前缀**区分：

| 代号 | 产物 | 触发 |
|---|---|---|
| **w** | Windows exe | 改 `app/**`、`tools/**`；或 `v*` tag |
| **a** | 安卓 APK | 改 `android/**`；或 `android-*` tag |

提交信息第一行加前缀可以强制指定：

```bash
git commit -m "a: 修安卓权限门禁"    # 只跑安卓
git commit -m "w: 修托盘图标"        # 只跑桌面
```

细节见 [`docs/ci.md`](docs/ci.md)。

---

## 实现要点

**桌面版**生成的轨迹要同时满足：

- 配速落在 `serMinPace ~ serMaxPace`
- 里程 ≥ 规则要求
- 围栏内比例 ≥ `scopePercentage`
- 采样点距落在 App 的过滤窗口 `1.39 ~ 13 m`
- 打卡点与 `signPoint` 对齐

**安卓版**的 GPS 注入改在 `LocationService.onLocationChanged` 里完成，
App 调用的每个方法（计距、配速、围栏判定、打卡、上传）都原样执行，
所以不依赖任何私有接口，也不碰签名链路。

轨迹噪声用 **AR(1)**（`n = 0.95n + 0.31σ·gauss`）而不是每拍独立噪声：
独立噪声会让相邻点位移互相叠加，3.5 km 能跑成 8.6 km，上报配速直接超出规则区间。

---

## 注意

- 仓库里的 `android/mobile/hf-release.jks`（口令 `android`）是自用签名，**不要拿本仓库做公开分发**
- 仅供学习研究，使用风险自负
