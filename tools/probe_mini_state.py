#!/usr/bin/env python3
"""小框现场探针：位置、widget.json、光标下的窗口、置顶状态。"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.ui.win32 import user32  # noqa: E402

user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

WM_NCHITTEST = 0x0084
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008


def find(class_name):
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


def rect(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def cls(h):
    c = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, c, 256)
    return c.value


def title(h):
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


def pid_of(h):
    p = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


mins = find("TokenBoardMini")
print("TokenBoardMini:", len(mins))
for h in mins:
    r = rect(h)
    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
    print(f"  hwnd={h} pid={pid_of(h)} rect={r} exstyle=0x{ex & 0xFFFFFFFF:08X} "
          f"topmost={bool(ex & WS_EX_TOPMOST)} vis={bool(user32.IsWindowVisible(h))}")
    grab_x = r[0] + 180
    grab_y = r[1] + 12
    pt = wintypes.POINT(grab_x, grab_y)
    under = user32.WindowFromPoint(pt)
    print(f"    抓取点=({grab_x},{grab_y})  光标下窗口={under} cls={cls(under)!r} "
          f"title={title(under)!r} pid={pid_of(under)}")
    lp = (grab_y << 16) | (grab_x & 0xFFFF)
    ht = user32.SendMessageW(h, WM_NCHITTEST, 0, lp)
    print(f"    对小框发 NCHITTEST -> {ht}（2=HTCAPTION 拖动区）")

from tokenboard.config import WIDGET_STATE_PATH
print("\nwidget.json:", WIDGET_STATE_PATH)
try:
    print("  ", open(WIDGET_STATE_PATH, encoding="utf-8").read())
except Exception as e:  # noqa: BLE001
    print("  读不到:", e)

pt = wintypes.POINT()
user32.GetCursorPos(ctypes.byref(pt))
print(f"\n当前鼠标位置=({pt.x},{pt.y})")
under = user32.WindowFromPoint(pt)
print(f"  鼠标下窗口={under} cls={cls(under)!r} title={title(under)!r}")
