# -*- mode: python ; coding: utf-8 -*-
"""打包免安装单文件版：dist/TokenBoard.exe（复制到任何地方都能双击运行）。"""

import os

block_cipher = None

ROOT = os.path.abspath(SPECPATH)
ICON = os.path.join(ROOT, "build", "tokenboard.ico")
# DPI manifest：不加的话 exe 在 150% 缩放下会被当成 DPI 无感知进程，界面按 1.0 倍画
MANIFEST = os.path.join(ROOT, "build", "app.manifest")

a = Analysis(
    ["run_gui.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "tokenboard", "data", "pricing.json"),
         "tokenboard/data"),
    ],
    hiddenimports=["zstandard", "zstandard.backend_c"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc_data", "test",
        "numpy", "PIL", "matplotlib", "pandas",
    ],
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
    name="TokenBoard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=ICON if os.path.exists(ICON) else None,
    version=os.path.join(ROOT, "build", "version_info.txt"),
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
)
