# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：python -m PyInstaller happyfuck.spec
import os

block_cipher = None
ROOT = os.path.abspath(SPEC)
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
        'coord', 'run_sim', 'rules', 'legym_envelope', 'b_login_upload',
        'paths',
    ],
    hookconfigfiles=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HappyFuck',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
