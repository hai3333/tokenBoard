#!/usr/bin/env python3
"""追踪 TokenBoard 窗口收到的所有 Win32 消息，定位「被最小化」的原因。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"D:\个人资料\项目\token看板"
NAMES = {
    0x0002: "WM_DESTROY", 0x000F: "WM_PAINT", 0x0010: "WM_CLOSE",
    0x0014: "WM_ERASEBKGND", 0x0020: "WM_SETCURSOR", 0x0024: "WM_GETMINMAXINFO",
    0x0100: "WM_KEYDOWN", 0x0111: "WM_COMMAND", 0x0113: "WM_TIMER",
    0x0200: "WM_MOUSEMOVE", 0x0201: "WM_LBUTTONDOWN", 0x0202: "WM_LBUTTONUP",
    0x0204: "WM_RBUTTONDOWN", 0x0205: "WM_RBUTTONUP", 0x020A: "WM_MOUSEWHEEL",
    0x0112: "WM_SYSCOMMAND", 0x0018: "WM_SHOWWINDOW", 0x0080: "WM_SETICON",
    0x0007: "WM_SETFOCUS", 0x0006: "WM_ACTIVATE", 0x0019: "WM_MOVE",
    0x0005: "WM_SIZE", 0x001C: "WM_SETMINMAXINFO", 0x0047: "WM_WINDOWPOSCHANGED",
    0x0084: "WM_NCHITTEST", 0x00A0: "WM_NCMOUSEMOVE", 0x0083: "WM_NCCALCSIZE",
    0x0210: "WM_ENTERSIZEMOVE", 0x0212: "WM_EXITSIZEMOVE", 0x0016: "WM_HOTKEY",
}
SC = {0xF060: "SC_CLOSE", 0xF020: "SC_MINIMIZE", 0xF030: "SC_MAXIMIZE",
      0xF010: "SC_MOVE", 0xF023: "SC_RESTORE"}

from tokenboard.ui import win32  # noqa: E402

orig_handle = win32.Window._handle
LOG = []


def traced(self, hwnd, msg, wparam, lparam):
    name = NAMES.get(msg, f"0x{msg:04X}")
    extra = ""
    if msg == 0x0112:  # WM_SYSCOMMAND
        extra = f"  cmd={SC.get(wparam & 0xFFF0, hex(wparam & 0xFFF0))}"
    if msg == 0x0200:
        extra = f"  at ({ctypes.c_short(lparam & 0xFFFF).value},{ctypes.c_short((lparam >> 16) & 0xFFFF).value})"
    if msg == 0x020A:
        raw = (wparam >> 16) & 0xFFFF
        extra = f"  delta_raw={raw} signed={ctypes.c_short(raw).value}"
    if msg == 0x0113:
        extra = f"  tid={wparam}"
    entry = f"{time.strftime('%H:%M:%S')}.{int(time.time() % 1 * 1000):03d} {name}{extra}"
    LOG.append(entry)
    return orig_handle(self, hwnd, msg, wparam, lparam)


win32.Window._handle = traced


def main():
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(2)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT, env=env)
    time.sleep(18)
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:  # noqa: BLE001
        p.kill()
    print("\n=== 消息序列（只显示非鼠标移动的）===")
    for e in LOG:
        if "WM_MOUSEMOVE" in e:
            continue
        print("  " + e)
    print(f"\n总消息 {len(LOG)} 条，WM_MOUSEMOVE "
          f"{sum(1 for e in LOG if 'WM_MOUSEMOVE' in e)} 条")


if __name__ == "__main__":
    main()
