# HappyFuck 乐奸

校园跑（乐健体育 `com.ledreamer.zz`）轨迹生成与自动提交的 PyQt6 桌面工具。

在真实高德地图上画跑道，按学校规则生成符合人类跑步特征的轨迹，定时自动提交，支持托盘后台运行。

## 目录结构

```
app/            PyQt6 主程序（入口 app/app.py）
tools/          轨迹几何 / 规则解析 / 登录上传的核心模块
.github/        CI 工作流
happyfuck.spec  PyInstaller 打包配置
```

## 本地运行

```bash
pip install -r requirements.txt
python app/app.py            # 或 python app/app.py --debug
```

## 打包 exe

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean happyfuck.spec
# 产物：dist/HappyFuck.exe（data/ 在 exe 同级目录生成）
```

## CI

- 每次 push / PR：`compileall` + Ruff（E9,F）语法与导入检查。
- 打 `v*` tag：Windows runner 自动 PyInstaller 打包，压缩为 `HappyFuck-<tag>-windows-x64.zip`，并创建 GitHub Release。

```bash
git tag v1.0.0 && git push origin v1.0.0
```
