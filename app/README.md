# HappyFuck 乐奸

乐健体育（com.ledreamer.zz，四川农业大学等高校校园跑）辅助工具，PyQt6 图形界面。

在真实高德地图上画跑道，按学校规则生成符合人类跑步特征的轨迹，定时自动提交，支持托盘后台运行。

---

## 实测状态（真实账号验证 2026-10-20）

| 环节 | 状态 | 说明 |
|---|---|---|
| 登录 | ✅ 已验证 | 手机号+密码，**服务端不校验登录签名**，无需任何前置配置 |
| 学期获取 | ✅ 已验证 | `GET education/semester/queryAll`，自动选 current 学期 |
| 规则拉取 | ✅ 已验证 | `POST running/app/getRunningLimit`（明文），自由跑 `hasRule=false` |
| token 续期 | ✅ 已验证 | 过期前自动续，refreshToken 轮换已处理 |
| 轨迹生成 | ✅ 已验证 | 人类行为模型，采样窗口 1.39~13m 零越界 |
| 规则体检 | ✅ 已验证 | 配速/里程/打卡点/围栏/空轨迹六维拦截 |
| 本地配额 | ✅ 已验证 | 日上限/最小间隔/连续失败熔断 |
| **上传** | ⚠️ **需校准** | 服务端 DTO 结构与静态推断不符，需抓一次真机包（见下） |

---

## 快速开始

### 1. 装依赖

```bat
"C:\Program Files\Python313\python.exe" -m pip install PyQt6 PyQt6-WebEngine frida frida-tools pycryptodome
```

### 2. 启动

```bat
python app.py
```

`python` 指向别的虚拟环境时，用启动器：

```bat
run.bat gui
```

### 3. 使用流程

1. 账号页填手机号密码 → 登录（不需要任何签名配置）
2. 地图上沿操场点 4~8 个点 → 闭合跑道
3. 刷步页「按规则自动填」→「预览轨迹」→「开始刷」
4. 定时页设时间点 → 启动调度 → 关窗最小化托盘继续跑

---

## 上传校准（一次性，需 root 安卓机）

**为什么**：登录/上传是两套加密栈。上传走 kernel 栈（`f.m.b.h.a`，salt `cee1833c…`），实测 4 种密钥×多种字段组合，服务端一律回「字段为 null」——静态无法确定服务端 DTO 确切形态，盲发只会消耗账号。

**怎么做**（只需一次）：

```bat
:: 1. 手机 USB 连电脑，运行 frida-server
:: 2. 电脑上：
python capture_run.py
:: 3. App 自动启动，自由跑 200~400 米，结束后正常上传
:: 4. 看到 [saved] → data/upload_sample.json 生成
```

之后「开始刷」按钮旁显示 ✅ 已校准，所有上传按真实结构回放（自动替换轨迹/时间/里程，保留字段骨架）。

---

## 技术要点

### 坐标系 GCJ-02

App 内零转换（`LocationService.java:1063`、`UniLatLngRespBean.java:121`）。WGS84 与 GCJ-02 差 500~700 米，用错直接出围栏。地图用高德瓦片（GCJ 切片）+ Leaflet（WGS84 投影），传 GCJ 坐标恰好对齐。

### 加密双栈

| 接口 | 方式 | salt |
|---|---|---|
| 登录 v2/manage/login | envelope `{t, pyd}` | `402881ea…`（native） |
| 学期/规则/续期 | **明文** | — |
| 上传 v3/upload | envelope `{t, pyd}` | `cee1833c…`（kernel，待抓包确认） |

密钥派生：`abs(t[2:5]-t[4:8]) << t[-1]` 拼 salt 取前 16 字节，AES-128-ECB-PKCS5。

### 采样窗口

相邻点距离必须 ∈ [1.39, 13.0] 米（`LocationService.V()`）。生成后按输出精度（7 位小数）量化再二次校验，避免舍入挤出边界。

### 防封号三层

1. 规则体检：配速区间/里程窗口/打卡点/围栏/采样窗口/空轨迹
2. 本地配额：日里程上限 + 最小间隔 + 连续失败熔断
3. 行为模拟：起步加速、疲劳衰减、呼吸节奏、GPS 噪声、随机丢点

---

## 项目结构

```
happyfuck/
├── app.py              入口
├── main_window.py      主窗口
├── map_panel.py        地图控件
├── tile_server.py      本地瓦片代理
├── service.py          业务服务层
├── uploader.py         上传模块（实测校准版）
├── scheduler.py        定时调度
├── history.py          上传历史与配额
├── config.py           配置持久化
├── theme.py            深色主题
├── widgets.py          通用组件（? 帮助）
├── capture_run.py      一键抓包校准
├── capture_upload.js   frida 钩子
└── assets/             地图页面 + Leaflet
```

---

## 安全建议

| 项 | 建议 |
|---|---|
| 频率 | 每天 1~2 次，间隔 ≥8 小时 |
| 配速 | 用「按规则自动填」，别贴边界 |
| 参数 | 定期「随机变化」 |
| 体检 | 保持开启 |
| 里程 | 别一次刷满配额 |

---

## 许可证

仅供学习研究。
