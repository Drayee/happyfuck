# HappyFuck 乐奸 —— 已知问题与解决方案记录（2026-10-20）

> 目的：当前会话可能随时丢失，本文档沉淀排查得到的关键事实与结论，
> 任何新会话直接读本文件即可接续，不必重新逆向/重新试错。

---

## 1. 上传字段语义（反编译 `RunningViewModel.n()` 确认，最重要）

⚠️ 曾经按「米 / 秒」猜着写，导致服务端可能判成绩无效。真实语义：

| VO 字段 | 类型 | 真实含义 | 备注 |
|---|---|---|---|
| `totalMileage` / `gpsMileage` / `effectiveMileage` | double | **公里**，setScale(4) | LocationService.O(): m/1000 |
| `effectivePart` | int | scoringType==1 → **恒 1** | 段距跑(==2)才是 int(km) |
| `totalPart` | double | **恒 0.0** | 仅 scoringType==2 = 段距 km |
| `avePace` | double | **毫秒/公里**（450s/km → 450000） | `a()`= runtimeMillis ÷ gpsKm |
| `paceNumber` | int | **步数**（非分钟数！） | 按步频 ~172 步/分模拟 |
| `calorie` | int | METs 公式 kcal | `f.l.c.e.a.d(paceMs, 体重kg, 距离m)`，已复刻为 `run_sim.calc_kcal` |
| `keepTime` | int | 秒 | round(runtimeMillis/1000) |
| `type` | String | RunTypeEnum.title | `'范围跑'` / `'自由跑'` / `'定点跑'`（不是 "1"！） |
| `deviceType` | String | Build MODEL+' '+BUILD.ID | 例 `Pixel 6`（不是 "android"！） |
| `startTime`/`endTime`/`signTime` | String | `"yyyy-MM-dd HH:mm:ss"` | 传毫秒字符串会整对象解析失败（实测 code 40001） |
| `endTimeDate` | long | 毫秒时间戳 | |

- 规则下发 `averageSpeedStart/End` 同为 **ms/km**（180000=3min/km）；里程边界是 km；`openTimes` 是当日 ms 偏移。
- `scopePercentage=30` = ≥30% 采样点落在围栏内（雅安围栏实测达标 ~80%，前提：跑道是"稠密内缩环"而非 9 点稀疏多边形）。
- `signPoint` 结构 = `{'signPoint': str(编号), 'state': 1}`，编号是规则 `signPoint` 数组下标；命中判定 50m。
- 上传接口 `running/app/v3/upload` **无 @SecurityAes** → 明文 JSON；实测 `code=0` 多次成功。
- 登录 `v2/manage/login` **不校验 signDigital**（空签名 code=0），登录不需要 Frida。
- token 寿命 ≈8h；`accessTokenExpires` 是服务端下发的过期毫秒戳。

## 2. UI 线程规则（PyQt6，血泪教训）

1. **`QTimer.singleShot(0, cb)` 从 Python `threading.Thread` 调用不会触发**（QTimer 仅限其创建线程）。
   service.py 全部走裸线程 + 回调，所以 **所有传给 `svc.*` 的 `on_done/on_progress/on_log` 都必须自己 marshal 回主线程**，统一用：
   ```python
   self._post_ui(lambda: ...)   # MainWindow 内置，基于主线程 QObject 的 QSocketNotifier 泵
   ```
   （`tile_server` 之外不要用 QSocketNotifier；见 main_window._UiPump。）
2. `functools.partial(lambda **kw: ...)` 放进 `QTimer.singleShot` 会因 Qt 把剩余参数按位置传入而报 `takes 0 positional arguments`。先包成零参 lambda 再调度。
3. `QWebEngineView` 必须在 `QApplication` **之前** import。
4. 后台运行需 `QApplication.setQuitOnLastWindowClosed(False)`，否则关窗即退进程；退出托盘走 `close()` → `hide()` 路径，不要 `sys.exit(0)`。

## 3. 环境与账号

- Python：`C:\Program Files\Python313\python.exe`；GUI 测试用 `QT_QPA_PLATFORM=offscreen`。
- 工作目录：脚本必须在 `work/qqbase-apk/happyfuck/` 下运行；tools 库在 `../tools`（config.TOOLS）。
- 真机：BlueStacks `emulator-5554`，ADB = `C:\Program Files\BlueStacks_nxt_cn\HD-Adb.exe`，包名 `com.ledreamer.zz`。
- **账号**：真实凭据不入库；本地 token 在 `data/session.json`（gitignored），首次使用在登录页填写手机号密码即可。
- 学校 id：`402881ea7c39c5d5017c39d134ca03ac`（当前学期）；demo 历史围栏文件里的 `...d143a8062b` 是**旧 native salt**，不是学校 id，别混。
- 2026-10-20 已真实上传成绩 3 条（3.07 / 3.24 km 等），日配额 5km、间隔 8h（本地防封）。

## 4. 范围跑核心链路（当前状态：✅ 全部打通）

1. 启动 → 地图就绪 → `_load_demo_fence()` 用 `data/range_2024-2025_1.json`（9 点凹多边形围栏）→
   `MainWindow._inset_loop()`（稠密边界采样 + 逐点内法线试探 + 闭合 Douglas-Peucker + 兜底收拢）
   → 23 顶点 / 4433m / 顶点全内部 → 写入 `self.waypoints` + 地图。
2. 登录（可跳过，范围跑 demo 不依赖登录）→ 拉规则 `fetch_rules`（当前学期 `hasRule=false`，正常；真机此时传 `lgs=''`、type='自由跑'——与代码一致）。
3. 「开始刷」→ `svc.run_once`：生成（TrackSim 1s 采样 + GPS 噪声 + V() 窗口过滤 1.39~13m）
   → 本地配额 → `rules.check`（配速/里程/围栏比例/采样窗口/打卡点）→ `uploader.upload` 明文 POST → 历史。
4. 实测 `run_once` 全链路真实上传 `code=0` 成功；VO 各字段值见上表。

## 5. 待办 / 已知边界

- 当前学期无规则：范围跑 demo 用历史围栏；**学期规则上线后要切 `data/range_real.json`**。
- `limitationsGoalsSexInfoId` 当前学期为 null：真机同样传空串，属正常；若 App 内成绩显示"无效"再回来查。
- 步频字段 VO 不存在，服务端可能按 routineLine 密度反推（已按 172 步/分生成采样密度）。
- frida-server 尚未在 BlueStacks 跑起来（`vendor/frida-server-17.24.3-android-x86_64` 已备好）；登录/上传都不需要它，仅 hs 表抓取需要。
- `tile_server.py` 已做抗断连/抗超时 + 透明占位瓦片（2026-10-20 a189267）。

## 6. Git 约定

每次任务完成 `git add . && git commit`，格式 `<type>(<scope>): <desc>`，**不自动 push**。
