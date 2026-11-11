#!/usr/bin/env python3
"""移除之前安装的副本（对齐「免安装」的选择）。"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tokenboard import install as inst

dest = inst.default_install_dir()
print(f"移除安装目录: {dest}")
inst.uninstall(dest, remove_data=False)

sm = Path(inst.START_MENU) / "TokenBoard.lnk"
dk = Path(inst.DESKTOP) / "TokenBoard.lnk"
print(f"  安装目录已删: {not dest.exists()}")
print(f"  开始菜单已删: {not sm.exists()}")
print(f"  桌面已删:     {not dk.exists()}")

import winreg
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, inst.REG_KEY):
        print("  注册表项仍存在 ❌")
except OSError:
    print("  注册表项已删 ✓")
