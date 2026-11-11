# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成 TokenBoard.exe（窗口模式，无控制台）。"""

import os

block_cipher = None

ROOT = os.path.abspath(os.getcwd())
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
    hiddenimports=[
        "zstandard",
        "zstandard.backend_c",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc_data", "test",
        "numpy", "PIL", "matplotlib", "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TokenBoard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # 桌面程序，不要控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON if os.path.exists(ICON) else None,
    version=os.path.join(ROOT, "build", "version_info.txt")
    if os.path.exists(os.path.join(ROOT, "build", "version_info.txt")) else None,
    manifest=MANIFEST if os.path.exists(MANIFEST) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TokenBoard",
)
