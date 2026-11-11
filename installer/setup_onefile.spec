# -*- mode: python ; coding: utf-8 -*-
"""打包单文件安装器：dist/TokenBoard-Setup-1.0.0.exe（双击即装）。"""

import os

block_cipher = None

ROOT = os.path.dirname(os.path.abspath(SPECPATH))   # 项目根目录
APP_DIST = os.path.join(ROOT, "dist", "TokenBoard")
ICON = os.path.join(ROOT, "build", "tokenboard.ico")

a = Analysis(
    [os.path.join(ROOT, "installer", "setup_main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (APP_DIST, "payload"),
    ],
    hiddenimports=["winreg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "test", "numpy", "PIL", "matplotlib", "pandas"],
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
    name="TokenBoard-Setup-1.0.0",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=ICON if os.path.exists(ICON) else None,
    version=os.path.join(ROOT, "build", "version_info.txt"),
)
