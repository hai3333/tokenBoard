# -*- mode: python ; coding: utf-8 -*-
"""打包安装器：把应用本体作为 payload 塞进 TokenBoard-Setup.exe。"""

import os

block_cipher = None

ROOT = os.path.dirname(os.path.abspath(SPECPATH))   # spec 在 installer/ 下，根目录是上一级
APP_DIST = os.path.join(ROOT, "dist", "TokenBoard")
ICON = os.path.join(ROOT, "build", "tokenboard.ico")

a = Analysis(
    [os.path.join(ROOT, "installer", "setup_main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # 应用本体整个目录作为 payload
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
    [],
    exclude_binaries=True,
    name="TokenBoard-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,           # 安装过程在控制台里显示，方便看进度
    disable_windowed_traceback=False,
    icon=ICON if os.path.exists(ICON) else None,
    version=os.path.join(ROOT, "build", "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="TokenBoard-Setup",
)
