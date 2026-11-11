#!/usr/bin/env python3
"""端到端测试安装器：安装 -> 校验 -> 启动 -> 卸载。"""
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\个人资料\项目\token看板")
SETUP = ROOT / "dist" / "TokenBoard-Setup" / "TokenBoard-Setup.exe"
INST = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "TokenBoard"
START_MENU = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TokenBoard"


def run_setup(args=(), answers=""):
    p = subprocess.run([str(SETUP), *args], input=answers, text=True,
                       capture_output=True, timeout=300)
    print(p.stdout)
    if p.stderr.strip():
        print("--- stderr ---")
        print(p.stderr[-2000:])
    return p


print("=" * 70)
print("1) 安装（回车确认，n 不启动）")
print("=" * 70)
run_setup(answers="\nn\n")

print("=" * 70)
print("2) 校验安装结果")
print("=" * 70)
print(f"  安装目录存在: {INST.exists()}  -> {INST}")
exe = INST / "TokenBoard.exe"
print(f"  主程序存在: {exe.exists()}  ({exe.stat().st_size if exe.exists() else 0} bytes)")
print(f"  开始菜单快捷方式: {(START_MENU / 'TokenBoard.lnk').exists()}")
print(f"  桌面快捷方式:     {(DESKTOP / 'TokenBoard.lnk').exists()}")
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        for name in ("DisplayName", "DisplayVersion", "UninstallString", "InstallLocation"):
            print(f"  注册表 {name}: {winreg.QueryValueEx(k, name)[0]}")
except OSError as e:
    print(f"  注册表读取失败: {e}")

print()
print("=" * 70)
print("3) 启动已安装的程序")
print("=" * 70)
proc = subprocess.Popen([str(exe)], cwd=str(INST))
time.sleep(10)
print(f"  进程存活: {proc.poll() is None}  (pid {proc.pid})")
import ctypes
from ctypes import wintypes
user32 = ctypes.windll.user32
wins = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def cb(h, _l):
    c = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, c, 256)
    if c.value == "TokenBoardWindow":
        wins.append(h)
    return True


user32.EnumWindows(cb, 0)
print(f"  窗口数: {len(wins)}")
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:  # noqa: BLE001
    proc.kill()

print()
print("=" * 70)
print("4) 卸载")
print("=" * 70)
run_setup(args=["--uninstall"], answers="\n")
print(f"  安装目录已删除: {not INST.exists()}")
print(f"  开始菜单快捷方式已删除: {not (START_MENU / 'TokenBoard.lnk').exists()}")
print(f"  桌面快捷方式已删除:     {not (DESKTOP / 'TokenBoard.lnk').exists()}")
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY):
        print("  注册表项仍存在 ❌")
except OSError:
    print("  注册表项已删除 ✓")
