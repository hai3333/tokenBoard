#!/usr/bin/env python3
"""测试单文件安装器：TokenBoard-Setup-1.0.0.exe"""
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\个人资料\项目\token看板")
SETUP = ROOT / "dist" / "TokenBoard-Setup-1.0.0.exe"
INST = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "TokenBoard"
START_MENU = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"
DESKTOP = Path(os.environ["USERPROFILE"]) / "Desktop"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\TokenBoard"


def run(args=(), answers=""):
    p = subprocess.run([str(SETUP), *args], input=answers, text=True,
                       capture_output=True, timeout=600)
    print(p.stdout[-1200:])
    if p.stderr.strip():
        print("--- stderr ---", p.stderr[-800:])
    return p


print("=" * 68)
print("1) 安装")
print("=" * 68)
t0 = time.time()
run(answers="\nn\n")
print(f"  耗时 {time.time() - t0:.1f}s")

print("=" * 68)
print("2) 校验")
print("=" * 68)
exe = INST / "TokenBoard.exe"
print(f"  安装目录:  {INST.exists()}")
print(f"  主程序:    {exe.exists()}")
print(f"  开始菜单:  {(START_MENU / 'TokenBoard.lnk').exists()}")
print(f"  桌面:      {(DESKTOP / 'TokenBoard.lnk').exists()}")
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        print(f"  卸载命令:  {winreg.QueryValueEx(k, 'UninstallString')[0]}")
except OSError as e:
    print(f"  注册表:    失败 {e}")

print("=" * 68)
print("3) 启动已安装程序")
print("=" * 68)
proc = subprocess.Popen([str(exe)], cwd=str(INST))
time.sleep(11)
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
print(f"  进程存活 {proc.poll() is None}   窗口数 {len(wins)}")
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:  # noqa: BLE001
    proc.kill()

print("=" * 68)
print("4) 卸载（走注册表里的卸载命令）")
print("=" * 68)
run(args=["--uninstall"], answers="\n")
print(f"  安装目录已删: {not INST.exists()}")
print(f"  快捷方式已删: {not (START_MENU / 'TokenBoard.lnk').exists()}")
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY):
        print("  注册表项仍存在 ❌")
except OSError:
    print("  注册表项已删 ✓")
