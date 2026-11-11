#!/usr/bin/env python3
"""检查进程/窗口的 DPI 感知状态与实际客户区尺寸。

DPI-unaware 的进程：请求 1320 物理像素，实际只给 880（按 96dpi 虚拟化），
界面会缩成一小块，而且按 GetDpiForWindow 算出来的坐标全是错的。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.windll.user32
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = ctypes.c_uint

CTX = {-1: "INVALID", 0: "UNAWARE", 1: "SYSTEM_AWARE", 2: "PER_MONITOR", -4: "PER_MONITOR_V2"}

found = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def cb(h, _l):
    c = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, c, 256)
    if c.value == "TokenBoardWindow":
        found.append(h)
    return True


user32.EnumWindows(cb, 0)
if not found:
    print("没找到 TokenBoardWindow")
    raise SystemExit(1)

h = found[0]
cr = wintypes.RECT()
user32.GetClientRect(h, ctypes.byref(cr))
wr = wintypes.RECT()
user32.GetWindowRect(h, ctypes.byref(wr))
dpi = user32.GetDpiForWindow(h)
ctx = user32.GetThreadDpiAwarenessContext()
print(f"hwnd={h}")
print(f"  窗口矩形     = {wr.right - wr.left}x{wr.bottom - wr.top} 物理像素")
print(f"  客户区       = {cr.right}x{cr.bottom}")
print(f"  GetDpiForWindow = {dpi}")
print(f"  感知上下文   = {ctx} ({CTX.get(ctx, ctx)})")
expect = 880 * dpi // 96
print(f"  期望客户区   = {expect}x{520 * dpi // 96}（880x520 逻辑 × {dpi/96}）")
print("  结论:", "正常" if cr.right == expect else "★ DPI 没按预期生效（界面会缩成一小块）")
