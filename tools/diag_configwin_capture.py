#!/usr/bin/env python3
"""配置窗口到底是歪的，还是 PrintWindow 抓歪了？

同时抓两种图：
* PrintWindow（DWM 重定向表面）—— 跨进程抓自绘窗口的老办法
* ImageGrab（直接抓屏幕区域）—— 用户眼睛看到的就是这个

再打印一遍窗口矩形 + 所有子控件（EDIT）的矩形，两边对不上就能定位。
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from wincap import capture_client  # noqa: E402

user32 = ctypes.windll.user32
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202


def find_windows(class_name):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == class_name:
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def children(hwnd):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, c, 64)
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        out.append((h, c.value, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def main() -> int:
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(1.5)
    exe = r"D:\software\TokenBoard\TokenBoard.exe"
    subprocess.Popen([exe], cwd=r"D:\software\TokenBoard")

    panel = None
    for _ in range(40):
        time.sleep(0.5)
        w = find_windows("TokenBoardWindow")
        if w:
            panel = w[0]
            break
    if not panel:
        print("没找到主面板")
        return 1

    gear_x = int((880 - 120 + 20) * 1.5)
    gear_y = int(15 * 1.5)
    lp = (gear_y << 16) | (gear_x & 0xFFFF)
    user32.SendMessageW(panel, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.15)
    user32.SendMessageW(panel, WM_LBUTTONUP, 0, lp)
    time.sleep(2.5)

    cws = find_windows("TokenBoardConfigWindow")
    if not cws:
        print("配置窗口没出来")
        return 1
    cw = cws[0]

    wr = wintypes.RECT()
    user32.GetWindowRect(cw, ctypes.byref(wr))
    cr = wintypes.RECT()
    user32.GetClientRect(cw, ctypes.byref(cr))
    print(f"配置窗口 hwnd={cw}")
    print(f"  窗口矩形   = ({wr.left},{wr.top})-({wr.right},{wr.bottom})")
    print(f"  客户区     = {cr.right}x{cr.bottom}")
    print(f"  可见       = {bool(user32.IsWindowVisible(cw))}")

    print("\n子控件（EDIT）:")
    for h, cls, l, t, w, hgt in children(cw):
        print(f"  {cls:<8} hwnd={h:<10} 屏幕({l},{t}) {w}x{hgt}")

    out = Path(r"D:\个人资料\项目\token看板\tools")
    img = capture_client(cw)
    img.save(out / "diag_printwindow.png")
    print(f"\nPrintWindow -> diag_printwindow.png {img.size}")

    try:
        from PIL import ImageGrab
        shot = ImageGrab.grab(bbox=(wr.left, wr.top, wr.right, wr.bottom),
                               all_screens=True)
        shot.save(out / "diag_screengrab.png")
        print(f"屏幕抓取   -> diag_screengrab.png {shot.size}")
        # 屏幕抓图再放大一点看是不是黑的（锁屏时会是黑图/桌面图）
        px = shot.convert("L").getextrema()
        print(f"  亮度范围 {px}（0,0 = 全黑，说明会话不可见）")
    except Exception as e:  # noqa: BLE001
        print("屏幕抓取失败:", e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
