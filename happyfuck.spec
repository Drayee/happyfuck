# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 6.x 打包配置：python -m PyInstaller --noconfirm --clean happyfuck.spec
import os

ROOT = os.path.dirname(os.path.abspath(SPEC))
APP = os.path.join(ROOT, 'app')
TOOLS = os.path.join(ROOT, 'tools')

a = Analysis(
    [os.path.join(APP, 'app.py')],
    pathex=[APP, TOOLS],
    binaries=[],
    datas=[
        (os.path.join(APP, 'assets'), 'assets'),
    ],
    hiddenimports=[
        # tools/ 下是运行时动态 sys.path 导入的，显式声明保证收进 bundle
        'coord', 'run_sim', 'rules', 'legym_envelope', 'b_login_upload',
        'paths',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HappyFuck',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
