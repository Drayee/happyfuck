# HappyFuck 手机版 —— 乐健「范围跑」一键刷课

> 本目录是桌面端 `happyfuck` 的手机移植版：**直接修改原版 APK**，装到普通安卓手机上即可使用，
> 不需要 root、不需要开发者选项、不需要连着电脑。

---

## 一、这是什么

原版 APK（`com.ledreamer.zz`，乐健体育 / QQbase）的跑课逻辑全部在 App 内部：
`LocationService` 收 GPS → 算里程/配速 → 判围栏 → 判打卡点 → 打包 VO → 用 native 签名 → 上传。

手机版做的事只有一件：**把「真实 GPS」换成「预先算好的围栏内轨迹」**，
其余全部交给 App 自己跑。因此：

- 上传报文由 App 原生代码生成（字段、单位、`signDigital` 全部真实）
- 服务端看到的是"一个正常 App 在正常跑步"，不是外部脚本伪造的请求
- 不注入任何第三方进程、不用 Frida、不用 Xposed

---

## 二、学生怎么用（三步）

1. **安装**：把 `happyfuck_mobile.apk` 传到手机，点击安装（允许"未知来源"）。
   如果手机里装过官方版，需要先卸载官方版（签名不同，不能覆盖安装）。
2. **登录**：正常打开 App，用学号/手机号登录，进入「范围跑」页面。
3. **开始跑步**：点「开始跑步」，然后放着别动。
   App 会按预置轨迹在校园围栏内"跑"，里程/配速实时增长；
   达到学校要求后点「结束」，App 自动上传成绩。

> 全程不需要电脑、不需要 root、不需要开开发者选项。
> 一次跑完约 26 分钟（3.5 km @ 7'30"/km），和真实跑步耗时一致。

### ⚠️ 前提：学校当前学期必须有生效的跑步规则

范围跑是**服务端下发**的功能（`running/app/getRunningRange` 需要
`patternId` / `scoringType` / `limitationsGoalsSexInfoId` / `semesterId`）。
如果学校当前学期没有生效规则（`semesterId` 为空、接口返回 400/503），
App 自己也进不去范围跑——这不是补丁问题。

遇到这种情况先确认：官方 App 里能不能正常进入「范围跑」页面。
官方能进，补丁版就能用；官方进不去，需要等学期规则生效。

---

## 三、工作原理（技术细节）

### 3.1 补丁点一览

| 位置 | 改动 | 目的 |
|---|---|---|
| `lib/arm64-v8a/libsecurity.so` @ `0x7ae4` | `b.ne` → `nop` | 绕过 `checkSignature` 的证书 hashCode 比对（`0x8f977ed0`），让重签名后 native 加密仍可用 |
| `LocationService.onCreate()` | 追加 `SyntheticGps.load()` + `startDriver()` | 启动时加载轨迹、起 1s 定时器 |
| `LocationService.onLocationChanged()` | 入口处 `SyntheticGps.inject(amapLocation)` | 把真实坐标覆盖为轨迹点 |
| `LocationService.r0()` | `startLocation()` → `nop` | 不启动真实高德定位，避免模拟器/室内无效坐标污染 |
| `LocationService.onDestroy()` | 追加 `SyntheticGps.stopDriver()` | 退出时停表 |
| `UniversityApplication$a.e()` | 追加 `SyntheticGps.load()` + `NativeProbe.probe()` | App 启动即加载轨迹；探针仅打日志 |
| 驱动 `syncSteps()` | 反射写 `f.l.a.g.a.d` + 触发回调 | 合成步频 172 步/分，避免「3.5km 但 0 步」 |
| `assets/hf_track.txt` | 新增 | 1575 个轨迹点（`lat,lon,speed`） |
| `classes7.dex` | 新增 | `com.ledreamer.hf.SyntheticGps` 编译产物 |

### 3.2 为什么必须打 native 补丁

`libsecurity.so` 的 `checkSignature` 会比对「当前 APK 证书 DER 的 Java `Arrays.hashCode`」
与硬编码常量 `0x8f977ed0`。重签名后证书变了 → 返回 `-2` → 全局标志 `flag[0xe0c0]` 不被清零
→ `getDyKey` / `getRnKey` / `signRunData` 全部走失败分支返回 `UNSIGNATURE`，登录和上传都会挂。

把 `0x7ae4` 的 `b.ne`（不等则跳失败）改成 `nop` 后，函数恒走成功分支、恒把 `flag` 清零，
native 加密完全恢复。**实测**：`getDyKey("1712345678901")` 返回
`6666402881ea7c39c5d5017c39d143a8062b`，与桌面端 Python 复现值逐字节一致。

### 3.3 为什么用反射调 `onLocationChanged`

`LocationService` 的 `runType`（字段名 `w`）决定分支：`0`=自由跑、`1`=范围跑、`2`=定点跑。
驱动在 `runType ∈ {0,1}` 时注入 —— 两种模式的轨迹都在围栏内，服务端都接受；
`2`（定点跑）需要按点位逐个打卡，注入连续轨迹会被判无效，故排除。

> 这样处理是因为：当学期 `hasRule=false` 时，App 可能把「范围跑」降级成「自由跑」，
> 只认 `runType==1` 会导致学生完全用不了。

`onLocationChanged(AMapLocation)` 是 `public` 方法，用 `getMethod(...)` 直接反射调用即可，
不需要写复杂 smali，也不需要 hook 高德 SDK。

### 3.4 轨迹是怎么来的

`tools/gen_track_asset.py` 复用桌面端已验证的算法：

1. 读学校围栏（`happyfuck/data/range_2024-2025_1.json`，9 点凹多边形）
2. `route_gen._inset_loop()` 生成围栏内稠密内缩环（100 顶点 / 4597.7 m，全部在围栏内）
3. 按目标配速 450 s/km 沿环 1s 采样 → 1575 个点 / 3.5 km
4. 叠加 3 m GPS 噪声 + `V()` 窗口过滤（1.39~13 m，与 App 内过滤一致）
5. 输出 `lat,lon,speed` 到 `assets/hf_track.txt`

**实测围栏内占比 100.0%**（服务端要求 ≥30%）。

---

## 四、防封设计

| 风险点 | 处理 |
|---|---|
| 配速异常 | 450 s/km（7'30"/km），落在规则区间 180~540 内 |
| 轨迹出围栏 | 内缩环 + 100% 围栏内；服务端 `scopePercentage` 判定安全 |
| 点距异常 | 1s 采样 @ 2.222 m/s ≈ 2.22 m/点，落在 App `V()` 窗口 1.39~13 m 内 |
| 步频/步数 | 驱动每秒写 `f.l.a.g.a.d` 并触发回调，按 172 步/分合成（与桌面端一致） |
| 卡路里 | 由 App 自身按配速/体重计算 |
| 报文签名 | App 原生 `signRunData` 生成 `signDigital`，与真机一致 |
| 设备指纹 | `deviceType` = `Build.MODEL + Build.ID`，由 App 自己取值 |
| 模式串味 | 只在 `runType ∈ {0,1}`（自由跑/范围跑）注入，定点跑(2)不碰 |
| 外部可控性 | `LocationService` 保持 `exported=false`，第三方 App 无法拉起 |
| 频率/配额 | 沿用学校服务端规则；桌面端 `QuotaGuard` 的日里程/间隔限制仍建议在服务端侧遵守 |

> **注意**：任何自动化都存在被风控识别的可能。本项目只保证"报文形态与真机一致"，
> 不承诺 100% 不被判定。建议按真实作息使用（每天 1 次、正常配速）。

---

## 五、构建

### 5.1 依赖

- JDK 17+（脚本默认 `C:/Program Files/Java/jdk-25`）
- Android SDK build-tools（`apksigner`、`d8`）+ `platforms/android-34/android.jar`
- Python 3（生成轨迹资产）
- `tools/apktool_3.0.3.jar`

### 5.2 一键构建

```bash
cd work/qqbase-apk
bash mobile/build_mobile.sh
# 产出: mobile/dist/happyfuck_mobile.apk
```

脚本会依次：生成轨迹 → apktool 重打包 → javac+d8 编译 `SyntheticGps` → 注入 `classes7.dex` → 签名 → 校验。

### 5.3 换学校 / 换学期

围栏数据在 `happyfuck/data/range_2024-2025_1.json`（或 `range_real.json`）。
换成本校围栏后重新跑 `build_mobile.sh` 即可，轨迹会自动重算。

### 5.4 调整目标里程/配速

编辑 `tools/gen_track_asset.py`：

```python
target_km = 3.5          # 目标里程
pace_s_per_km = 450      # 配速（秒/公里），需落在学校规则区间内
noise_m = 3.0            # GPS 噪声幅度
```

---

## 六、已知限制

1. **覆盖自由跑 + 范围跑**（`runType ∈ {0,1}`）。定点跑(2)因需逐点打卡，仍走真实 GPS。
2. **轨迹是预生成的**，跑完 1575 点后循环。若单次跑超过 26 分钟，轨迹会重复；
   建议按目标里程结束。
3. **围栏必须匹配**。若学校改了围栏而没重新生成资产，轨迹会出界 → 被判无效。
4. **签名与官方版不同**，无法覆盖安装，需先卸载官方版（会清掉本地登录态）。
5. **arm32 未打 native 补丁**。仅 `arm64-v8a` 的 `libsecurity.so` 做了 `nop`；
   纯 32 位老机型需自行按同样思路补 `armeabi-v7a`（`checkSignature` @ `0x5d49`，Thumb）。
6. **模拟器/无 GPS 环境**已验证；真机首次使用建议先用小号试跑一次。
7. **依赖学校当前学期有生效的跑步规则**。规则未生效时 App 自身无法发起范围跑（见上文前提）。

---

## 七、与桌面版的关系

| | 桌面版 `happyfuck` | 手机版 `mobile/` |
|---|---|---|
| 运行位置 | PC（PyQt6） | 手机 App 内 |
| 登录/上传 | 纯 Python 直连 HTTP | App 原生 Retrofit + native 签名 |
| 轨迹来源 | 同一套 `route_gen`/`run_sim` | 同一套算法预生成资产 |
| 需要 root | 否 | 否 |
| 需要 Frida | 否（上传为明文 JSON） | 否 |
| 适用场景 | 批量、调试、抓包 | 学生日常一键使用 |

桌面版用于**研究与验证**，手机版用于**实际使用**。两者共享同一套轨迹算法与围栏数据。

---

## 八、文件清单

```
mobile/
├── README.md                  本文档
├── build_mobile.sh            一键构建脚本
├── hf-release.jks             签名密钥（自签名，口令 android）
├── src/com/ledreamer/hf/
│   └── SyntheticGps.java      轨迹加载 + 1s 驱动 + 注入
├── stub/com/amap/api/location/
│   └── AMapLocation.java      编译期桩类（不进 dex）
├── build/                     构建中间产物（gitignore）
└── dist/
    └── happyfuck_mobile.apk   最终产物（gitignore）
```

---

## 九、已知原生限制：`signDigital` 与 DexVMP

### 现象

重签名后，`Rengis.it(context)` 返回 **false**，导致 `Rengis.hs(str)` 返回 **null**，
原版 `RunningViewModel.n()` 会抛：

```
java.lang.NullPointerException: hs(key) must not be null
at RunningViewModel.n(SourceFile:41)
```

### 根因

`cn.legym.ai.util.Rengis` 不在任何 dex 里，由 `libdexvmp.so` 在运行时注入，
真正实现在 `libsportaction.so`（JNI 导出 `Java_cn_legym_ai_util_Rengis_it/hs/getFlavor`）。
该 so 内部有 `getPackname` / `getSignature` 辅助函数，**`it()` 会校验 APK 签名**。
重签名后校验失败 → `it()` 返回 false → `hs()` 返回 null。

> 注意：这层校验和 `libsecurity.so` 的 `checkSignature` 是**两套独立机制**。
> 我们已经 nop 掉后者（所以 `getDyKey` / `signRunData` 都能正常工作），
> 但前者在 `libsportaction.so` 里，且该 so 的节头/动态段被抹，无法按符号定位。

### 当前处理

`RunningViewModel.n()` 已打补丁：**`hs()` 返回 null 时回退为空串**，不再崩溃。

```
if-nez v0, :hf_sign_ok
const-string v0, ""
:hf_sign_ok
```

### 影响

| 场景 | 结果 |
|---|---|
| 学校当学期 `hasRule=false` | 服务端不校验 `signDigital`，空串可上传（桌面端已实测 code=0） |
| 学校有严格规则校验 | 服务端可能拒绝空 `signDigital`，需要在真机上验证 |

### 如果要彻底解决

需要拿到真实的 `hs(输入)→输出` 对，再决定是复刻算法还是建表：

1. 找一台**能 root** 的真机，装**原版** APK（不要重签名）
2. 跑 `frida-server`，hook `cn.legym.ai.util.Rengis.hs` 打印入参/出参
3. 用这些样本判断算法（`ToHS` + SHA1 + `ByteToHexStr`，可能带 salt），
   在 `SyntheticGps` 里用 Java 复刻，再 patch `RunningViewModel.n()` 调到我们的实现

> 桌面端 `happyfuck` 的 `hs_table.json` 就是这个思路的产物（半自动表）。

---

### 九之补充：为什么这条限制没法在本机验证/绕过

> 2026-10-22 实测记录

1. **本机 BlueStacks 5.22.170 无法 root**
   - `/system/xbin/su` 存在且有 setuid，但执行后无任何输出、连重定向文件都不创建 → 实际未启用
   - 该版本没有 `C:\ProgramData\BlueStacks_nxtluestacks.conf`（Hyper-V 版布局）
   - 社区反馈：BS 5.22.130+ 已移除 root；旧教程依赖的 BSTweaker 停在 BS 5.12
2. **没有 root 就跑不了 frida-server**，拿不到 `Rengis.hs` 的真实入参/出参
3. **延迟调用也救不回来**
   - 在 LocationService 驱动里第 3/6/10 秒各重试一次 `Rengis.it()`，仍全部 `false`
   - 排除「Application.onCreate 阶段调用太早」的可能，确认是签名绑定
4. **静态逆向受阻**
   - 补充：`signRunData` 经反汇编确认只调 `GetFieldID`/`GetObjectField`，
     **没有任何 `SetObjectField`** —— 它不会改写 `signDigital`，
     所以最终报文里的 `signDigital` 就是 `hs()` 的返回值（空串）
   - `libsportaction.so`：节头被抹（节名全是 ELF 魔数）、`PT_DYNAMIC` 里没有
     `DT_SYMTAB/DT_STRTAB/DT_HASH`，无法按符号定位 `Rengis_it`
   - `libdexvmp.so`：有 `.dynsym` 但符号名混淆（`j__IIOII$I0I55lI0SIIOIlS5$_...`）；
     `Rengis/Flavor/hs/it/XXYY` 这些字符串在 0x6a5c0 附近，但全 `.text`
     没有 `adrp+add` 直接引用它们，说明 JNI 表是运行时拼的

### 如果要继续攻这条线，需要准备的环境

| 方案 | 成本 | 说明 |
|---|---|---|
| 降级 BlueStacks 到 5.22.125 及更早 | 中 | 有 root，但可能丢失现有数据 |
| 装 LDPlayer 9 / MuMu | 中 | 设置里一键开 root，最省事 |
| 真机 root（Magisk） | 高 | 最贴近真实环境 |
| 真机 + 未修改原版 APK + Frida | 高 | 只为抓 `hs` 样本，不需要 root 也能用 gadget 重打包——但那又回到重签名问题 |

拿到样本后的判断顺序：
1. 先试 `SHA1(输入)`、`SHA1(输入+salt)`、`MD5` 等最可能的构造
2. 对不上就 dump `ToHS` 的汇编（`libsportaction.so` 未加壳，熵只有 4.25）
3. 实在不行就建表（输入空间含时间戳，表不可行）→ 只能复刻算法

## 十、定位相关补丁

| 问题 | 补丁 |
|---|---|
| 部分 ROM 误判「没有定位权限」弹模态框阻断 | `PermissionUtil.checkLocationPermission` / `checkLocationService` 恒返回 true |
| 真实高德定位在模拟器/室内返回无效坐标，污染距离计算 | `LocationService.r0()` 的 `startLocation()` 改 `nop` |
| App 启动前 JS 层 `uni.getLocation` 失败 | **未绕过**：需要真机有 GPS。学生在本校范围内正常使用即可 |

> `uni.getLocation` 走的是 DCloud 的 `DLGeolocation`，独立于 `LocationService`。
> 若强行返回合成坐标，还要处理 GCJ-02/WGS84 转换语义（JS 层会把 `gcj02` 转 WGS84），
> 风险大于收益，故保留真实定位。

---

## 十一、为什么 BlueStacks 里 App 是白屏（原版也一样）

> 2026-10-22 实测，与补丁无关

### 现象

安装后进程正常启动、`HF_LOAD points=1575`、无崩溃，但画面是一片白，只有状态栏时间。

### 定位过程

| 步骤 | 结果 |
|---|---|
| 装**原版** `QQbase(1).apk` | **同样白屏** → 排除补丁因素 |
| 用 App 自带 `WebViewActivity` 加载百度 | **正常渲染** → 排除 WebView 本身 |
| `uiautomator dump` 白屏页 | 只有嵌套 `FrameLayout`，WebView 内无 DOM |
| 网络 `ping cpes.legym.cn` | 10ms 正常 |
| `assets/apps/__UNI__DEAC2C5/www/` | `__uniappview.html` / `app-service.js` / `app-view.js` 齐全 |
| logcat | **见下** |

```
WeexCore: jsengine#weexcore fork child succes!        ← JS 引擎子进程起来了
WeexCore: IPCException server spinWaitPeer timeout    ← 共享内存 IPC 超时
WeexCore: JSFramwork init start sender is null
weex:     invokeInitFramework ExecuteJavaScript fail
weex:     execJSService: framework.js uninitialized   ← JS 框架没初始化
```

### 结论

这个 App 的 UI 跑在 **Weex** 上：主进程 fork 出 `jsengine#weexcore` 子进程，
通过 `IPCFutexPageQueue`（共享内存 futex）做 IPC，再加载 `libweexjss.so`（13.5MB 的
JavaScriptCore）执行 `framework.js`。

BlueStacks 是 **x86_64 + ARM 翻译**（`primaryCpuAbi=arm64-v8a`），
这种「多进程共享内存 + futex」的 ARM 原生 IPC 在翻译层上会超时，
导致 JS 框架永远初始化不了 → 白屏。

**关键点**：原生层（`LocationService`、定位、上传）是普通 Kotlin，翻译层扛得住，
所以我们的 GPS 注入能正常跑（`gpsDist` 持续增长）；但 UI 依赖 Weex JS，跑不起来。

### 对使用的影响

| 场景 | 是否可用 |
|---|---|
| 真机（ARM） | 正常，Weex 原生执行 |
| BlueStacks / LDPlayer / MuMu（x86 + ARM 翻译） | **大概率白屏**，不保证 |
| 云真机 / ARM 服务器模拟器 | 正常 |

**结论：蓝叠只能用来验证原生链路（GPS 注入、里程计算），不能用来验证 UI 和完整跑课流程。
真正要跑，必须用真机。**

---

## 十一、自定义跑道：手动画圈 → 关键点 → 实时加噪

### 11.1 两种模式

| 模式 | 资产 | 行为 | 轨迹可复现 |
|---|---|---|---|
| **关键点（推荐）** | `hf_route.txt` | 稀疏闭环顶点，运行时按配速沿折线插值 + 随机 GPS 噪声 | ❌ 每次不同 |
| 固定点（兼容） | `hf_track.txt` | 1575 个预生成点逐点回放 | ✅ 完全一致 |

`SyntheticGps.load()` 的查找顺序：

1. `/sdcard/Android/data/com.ledreamer.zz/files/hf_route.txt` ← **外部，免重建**
2. `assets/hf_route.txt` ← 内置
3. 外部 / 内置 `hf_track.txt` ← 退回固定点模式

### 11.2 画圈

```bash
run.bat gui
# 或  python tools/map_editor.py
```

1. 左键在地图上点出闭环顶点（≥3 个）
2. 点「**③ 导出关键点（手机版用）**」
3. 得到 `hf_route.txt`

导出时会用 `route_gen._resample_loop(step_m=40)` 把顶点重采样成等距关键点，
避免手点太稀疏、插值后走直线切角跑到围栏外。

### 11.3 换圈不用重签 APK

```bash
adb push hf_route.txt /sdcard/Android/data/com.ledreamer.zz/files/hf_route.txt
```

App 下次启动即生效（`SyntheticGps.load()` 优先读外部文件）。
文件管理器直接把文件放到该目录也可以。

### 11.4 文件格式

```
# 注释行，随便写
pace=450          # 秒/公里（7'30"/km），需落在学校规则区间内
noise=0.9         # GPS 噪声标准差（米），对齐桌面端 run_sim 的 gps_noise
cadence=172       # 步/分钟
29.9821874,102.9864419   # 关键点，闭环，至少 3 个
29.9817397,102.9864325
...
```

### 11.5 运行时行为

每 1 秒 tick 一次：

```
d       = (1000 / pace) * elapsed              # 已跑距离
base    = pointAt(d % 一圈长度)                 # 沿闭环折线插值
n       = AR(1): n = 0.95*n + 0.31*noise*gauss  # 时间相关噪声（米）
lat/lon = base + n（换算成度）
speed   = 1000 / pace                           # m/s
```

**为什么必须是 AR(1) 而不是每 tick 独立噪声**：

| 噪声模型 | 有效里程（设定 3.5km） | 推算配速 |
|---|---|---|
| 独立 3.0m 圆盘 | **8.58 km** | 快了 145% |
| 独立 0.9m 高斯 | 3.89 km | 快 11% |
| **AR(1) 0.9m** | **3.51 km** | **449 s/km（设定 450）** |

独立噪声会让相邻采样点的位移互相叠加，里程越跑越虚高；
AR(1) 让噪声缓慢漂移（接近真实 GPS 的短时相关性），
绝对偏移仍有 ~0.9m 的真实感，但不会污染距离计算。

实测数据（`hf_route.txt`，100 关键点 / 闭环 4598m）：

```
有效里程 3.506 km   围栏内 83.9%   点距 0.76~3.12 m
```

> 围栏内比例不是 100%：围栏是凹多边形，`_inset_loop` 生成的环在若干顶点处
> 仍贴着边界（最近 0.2m）。试过「朝质心缩放」和「沿法线推移」两种修正，
> 在凹顶点处都会失效，因此保留原样 —— 84% 远高于服务端 30% 的判定阈值。
>
> 点距窗口：App 内部 `V()` 会丢弃相邻点距 <1.39 m 或 >13 m 的采样。
> AR(1) 0.9m 下点距 0.76~3.12 m，全部落在窗口内。

---

## 十二、App 内轨迹编辑器（手动画圈 + 显示围栏 + 持久化）

### 12.1 入口

**长按桌面图标 → 「设计跑步轨迹」**（Android 7.1+ 快捷方式，见
`res/xml/hf_shortcuts.xml`）。

低版本或快捷方式没出来时，用 adb 直接拉起：

```bash
adb shell am start -n com.ledreamer.zz/com.ledreamer.hf.RouteEditorActivity
```

> Activity 设为 `exported="true"`，所以第三方「快捷方式」类 App 也能创建入口。

### 12.2 界面

```
┌─────────────────────────────────┐
│ 顶点 12 | 周长 1834 m | 跑完约 14min │  ← 顶部状态
│ 红色虚线 = 学校围栏，请在它内部点圈   │
├─────────────────────────────────┤
│                                 │
│        高德地图（可缩放拖动）        │
│     ⬤────⬤                      │
│    /      \      ← 蓝色折线       │
│   ⬤       ⬤                     │
│    \_____/  ← 红色虚线为围栏       │
│                                 │
├─────────────────────────────────┤
│  撤销  |  清空  |  保存  |  关闭   │
└─────────────────────────────────┘
```

- 地图上**单击**加点
- 顶点 ≥3 且周长 ≥50m 才能保存
- 保存后 `SyntheticGps.load()` 立即热加载，不用重启 App

### 12.3 围栏从哪来

围栏是服务端下发的（`running/app/getRunningRange` 的 `data.rangeRunningRegion`），
App 里由 `LocationService.h`（AMap `Polygon`）持有。

抓取时机：**第一次点「范围跑」并开始跑的前 3 秒**，
`SyntheticGps.saveFenceFromService()` 反射读取该 Polygon 并存到
`<filesDir>/hf_fence.txt`。

编辑器打开时：
1. 先读 `hf_fence.txt` 画红色虚线
2. 没有就尝试直接反射读 `LocationService.h`（若此时正好在跑）
3. 都没有 → 不画围栏，仍可画圈（坐标靠地图自行定位）

> 所以**先跑一次再画圈**，编辑器里才有围栏参考。

### 12.4 持久化

| 内容 | 路径 | 说明 |
|---|---|---|
| 轨迹 | `<filesDir>/hf_route.txt` | 主存储，卸载才清 |
| 轨迹副本 | `<getExternalFilesDir>/hf_route.txt` | 方便 adb pull/push 排查 |
| 围栏 | `<filesDir>/hf_fence.txt` | 抓到后常驻 |

`SyntheticGps.load()` 的加载顺序：

```
1. /sdcard/Android/data/com.ledreamer.zz/files/hf_route.txt   （外部，adb 可换）
2. <filesDir>/hf_route.txt                                     （App 内画圈保存）
3. assets/hf_route.txt                                         （内置默认）
4. hf_track.txt                                                （固定点回退）
```

### 12.5 坐标系

地图返回的 `LatLng` 是 **GCJ-02**，与跑步引擎、服务端围栏完全一致，
全程零转换。

---

## 十三、每日自动跑（半自动 / 全自动可切）

### 13.1 入口

长按桌面图标 → 「设计跑步轨迹」 → 底部点「**自动**」。

弹窗里可以设：

| 项 | 说明 |
|---|---|
| 启用每日自动跑 | 总开关 |
| 模式 | **半自动**：到点发通知，点一下开跑<br>**全自动**：到点直接开跑（需悬浮窗权限） |
| 每天触发时间 | 时:分 |
| 目标距离 | 公里，跑到即自动收尾上传 |
| 立即试跑 | 不等定时，马上验证一次 |

### 13.2 第一次必须先手动跑一次

自动跑需要三样东西：

```
serRuleCondition   (Parcelable)  学期/时间窗/配速区间
userInfo           (Parcelable)  用户信息
rangeLatLngJson    (String)      围栏 JSON
```

这些是 Parcelable，没法手搓。所以设计成「**学一次，回放 N 次**」：

第一次真实跑范围跑时，`HfAutoRun.captureIntentExtras()` 会把它们
序列化到 `<filesDir>/hf_intent.bin`；之后每天 `Parcel.unmarshall` 回放。

> 没跑过就点自动跑，会提示「还没有基准参数」。

### 13.3 执行链路

```
AlarmManager.setExactAndAllowWhileIdle(每天 HH:MM)
  ↓
HfDailyReceiver.onReceive()
  ├ 今天跑过？→ 跳过
  ├ 开关关着？→ 跳过
  ├ 没有缓存参数？→ 通知提醒先手动跑一次
  └ 按模式：
      全自动 → startActivity(RangeRunningActivity)
              失败（后台启动被拦）→ 自动降级为通知
      半自动 → 发通知「点我开始」
  ↓
RangeRunningActivity 正常跑（SyntheticGps 注入）
  ↓
每 1s tick：HfAutoRun.checkAndFinish()
  读 LocationService.INSTANCE.g().getGpsTotalDistance()
  >= 目标距离 → 反射调用 RunningActivity.S()
  ↓
S() → 停服务 → 算值 → 构建 VO → 上传
```

**`S()` 是 public final 的收尾入口**，直接反射调用即可跳过
「确认结束跑步」弹窗。

### 13.4 权限清单

| 权限 | 用途 | 用户是否需手动开 |
|---|---|---|
| `SCHEDULE_EXACT_ALARM` | 精确闹钟（Android 12+） | 是，设置里「闹钟和提醒」 |
| `SYSTEM_ALERT_WINDOW` | **全自动**模式后台启动 Activity | 是，悬浮窗/后台弹出界面 |
| `POST_NOTIFICATIONS` | 半自动模式通知（Android 13+） | 是 |
| `RECEIVE_BOOT_COMPLETED` | 重启后重排闹钟 | 否 |

**国产 ROM 还要额外设置**（否则容易「今天跑了明天不跑」）：

1. 自启动白名单
2. 电池优化 → 无限制
3. 多任务界面下拉加锁

### 13.5 日志

```bash
adb logcat -s HF_AUTO:* HF_ALARM:* HF_SCHED:* HF_LOAD:* HF_DRV:*
```

| 日志 | 含义 |
|---|---|
| `HF_SCHED: scheduled at ...` | 闹钟已排 |
| `HF_ALARM: on receive` | 到点触发 |
| `HF_AUTO: startRun ok (armed)` | 已拉起跑步页 |
| `HF_AUTO: target reached: 3.51 km` | 到目标，准备收尾 |
| `HF_AUTO: S() invoked` | 已触发结束+上传 |

`startRun failed (后台启动被系统拦截？)` → 去开悬浮窗权限，或改用半自动。

---

## 十四、日志：应用内可看 + 落盘到应用目录

不需要 adb，学生自己就能看到发生了什么。

### 14.1 应用内查看（两个入口）

**入口 A（推荐）：长按桌面图标 → 「运行日志」**

独立日志页 `HfLogActivity`，不加载地图，打开很快。
整屏日志 + 顶部行数提示 + 底部四个按钮（刷新 / 清空 / 路径 / 关闭），
打开自动滚到最新一行。

**入口 B：长按图标 → 设计跑步轨迹 → 底部「日志」**

弹窗版 `HfLogViewer`，看图顺便看日志时用。

两条入口读的是同一个 `hf_log.txt`。

### 14.2 落盘位置（同时写两处）

| 位置 | 路径 | 特点 |
|---|---|---|
| 应用内 | `<filesDir>/hf_log.txt` | 卸载才清，最稳 |
| 外部 | `/sdcard/Android/data/com.ledreamer.zz/files/hf_log.txt` | 文件管理器能看到，可直接复制发出来 |

点「文件位置」会显示这两个完整路径。

### 14.3 实现方式

所有自有模块的日志从 `android.util.Log` 换成 `HfLog`：

```java
HfLog.i("HF_AUTO", "target reached");
// → 同时写 logcat 和 hf_log.txt
```

- 单行格式：`MM-dd HH:mm:ss.SSS I/TAG: message`
- 文件超过 512KB 自动丢掉前半段，不会无限增长
- `HfLog.init(ctx)` 在 App 启动、两个 Receiver、编辑器打开时都会调用（幂等）

### 14.4 日志对照

| 日志 | 含义 |
|---|---|
| `HF_SCHED: scheduled at ...` | 闹钟排好了 |
| `HF_ALARM: boot event` | 开机重排 |
| `HF_ALARM: on receive` | 到点触发 |
| `HF_AUTO: startRun ok (armed)` | 已拉起跑步页 |
| `HF_LOAD: route mode: waypoints=100` | 轨迹加载成功 |
| `HF_DRV: start, class=...` | 驱动启动 |
| `HF_AUTO: target reached: 3.51 km` | 到目标 |
| `HF_AUTO: app distance unavailable, fallback...` | 主备反射都没通，用了估算兜底 |
| `HF_AUTO: S() invoked` | 已触发结束+上传 |

> 上传成没成功，看 App 自己的 `RunningViewModel` 日志（也会落到同一个文件里
> 吗？不会 —— 那是 App 的 `android.util.Log`，只在 logcat）。
> 要判断上传结果，用「数据上传成功」的界面提示，或 adb logcat 看
> `RunningViewModel: apiUploadRunInfoReq -> error = ...`。

---

## 十五、踩坑记录（装不上 / 地图空白）

### 15.1 MIUI 装不上：`解析软件包时出现问题 (33) packageInfo is null`

**现象**：蓝叠能装，真机（MIUI）装不上，报 `packageInfo is null`。

**原因**：`AndroidManifest.xml` 里给我们的 Activity 写了**裸中文 label**：

```xml
<activity android:name="com.ledreamer.hf.RouteEditorActivity"
          android:label="跑步轨迹"/>          <!-- ← 元凶 -->
```

apktool 会把这种裸字符串原样写进二进制 manifest 的字符串池，
AOSP 的 PackageParser 能读，但 MIUI 的解析器会失败 → `getPackageArchiveInfo` 返回 null。

**注意**：`aapt` / `aapt2 dump badging`、`zipalign -c`、`apksigner verify` **全部通过**，
所以工具层面完全看不出问题，只有真机会炸。

**修法**：改成字符串资源引用

```xml
<activity android:name="com.ledreamer.hf.RouteEditorActivity"
          android:label="@string/hf_shortcut_label"/>
```

> 规则：**manifest 里永远不要写裸中文/非 ASCII 字符串**，一律走 `@string/`。

### 15.2 地图一片灰：`errorCode 555570 隐私合规校验失败`

**现象**：编辑器能打开、按钮正常，但地图区域全灰，没有瓦片。

**日志**：

```
E 3dmap: 隐私合规校验失败：
E 3dmap: errorCode : 555570
E 3dmap: 原因：确保调用SDK任何接口前先调用更新隐私合规 updatePrivacyShow、
         updatePrivacyAgree 两个接口并且参数值都为 true，若未正确设置有崩溃风险
```

**原因**：高德地图 SDK 要求在用任何接口前声明隐私合规。
App 自己的地图页（`RangeRunningActivity` / `GpsSignActivity`）都在 `onCreate` 里调了，
我们新建的编辑器漏了；直接从快捷方式拉起时没走 App 的隐私弹窗流程，更是一定会命中。

**修法**：`new MapView()` **之前**调用

```java
MapsInitializer.updatePrivacyShow(this, true, true);
MapsInitializer.updatePrivacyAgree(this, true);
```

### 15.3 编辑器首次打开镜头在国家视角

因为没有围栏缓存，`moveCameraToFenceOrRoute()` 没有中心点可去。
跑过一次范围跑后 `hf_fence.txt` 就有内容，之后打开会自动定位到学校。
顶部提示会明确写「还没拿到学校围栏：先跑一次范围跑」。

### 15.4 真机安装验证清单

```bash
# 1) 文件大小必须完全一致（传输截断是 packageInfo is null 的另一大原因）
#    111.7 MB / 117,123,786 字节
# 2) 优先用数据线或 adb 安装
adb install -r happyfuck_mobile.apk
# 3) 装完长按图标，应出现两条：设计跑步轨迹 / 运行日志
```

微信文件传输上限 100MB，直接发 APK 会失败或截断——用数据线，
或先出 arm64 精简版（去掉 `lib/armeabi-v7a`，约 93MB）。
