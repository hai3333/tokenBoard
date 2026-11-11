#!/usr/bin/env python3
"""枚举当前所有 TokenBoardWindow（以及同名类）窗口：数量、位置、尺寸、所属进程。"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

user32 = ctypes.windll.user32
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

rows = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def cb(h, _l):
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, cls, 256)
    if "TokenBoard" not in cls.value:
        return True
    txt = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, txt, 256)
    wr = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(wr))
    cr = wintypes.RECT()
    user32.GetClientRect(h, ctypes.byref(cr))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    rows.append((h, cls.value, txt.value, pid.value,
                 (wr.left, wr.top, wr.right, wr.bottom),
                 (cr.right - cr.left, cr.bottom - cr.top),
                 bool(user32.IsWindowVisible(h))))
    return True


user32.EnumWindows(cb, 0)
print(f"找到 {len(rows)} 个 TokenBoard 相关窗口")
for h, cls, txt, pid, wr, cr, vis in rows:
    print(f"  hwnd={h:<10} pid={pid:<8} vis={vis} cls={cls} title={txt!r}")
    print(f"      window=({wr[0]},{wr[1]})-({wr[2]},{wr[3]})  client={cr[0]}x{cr[1]}")
