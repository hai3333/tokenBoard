#!/usr/bin/env python3
"""诊断：点击前后枚举所有 TokenBoardWindow 的状态。"""
import ctypes
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

VIEW_SEG_X = 16 + 152
VIEW_SEG_W = 60
VIEW_SEG_Y = 16 + 24


def enum_windows(tag):
    rows = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow":
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            cr = wintypes.RECT()
            user32.GetClientRect(h, ctypes.byref(cr))
            rows.append((h, user32.IsWindowVisible(h), user32.IsIconic(h),
                         (r.left, r.top, r.right, r.bottom),
                         (cr.right - cr.left, cr.bottom - cr.top)))
        return True

    user32.EnumWindows(cb, 0)
    print(f"--- {tag} ---")
    for h, vis, icon, rect, client in rows:
        print(f"  hwnd={h} visible={vis} iconic={icon} rect={rect} client={client}")
    return rows


def main():
    rows = enum_windows("初始")
    if not rows:
        print("!! 没有窗口")
        return 1
    hwnd = rows[0][0]
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1)

    rows = enum_windows("恢复后")
    hwnd = max(rows, key=lambda x: x[4][0])[0]

    scale = 1.5
    dx = VIEW_SEG_X + VIEW_SEG_W * 2.5
    dy = VIEW_SEG_Y + 12
    lparam = (int(dy * scale) << 16) | (int(dx * scale) & 0xFFFF)
    print(f"\n点击客户端坐标 ({dx},{dy}) -> lparam=0x{lparam:08X}")
    user32.SendMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.2)
    enum_windows("WM_MOUSEMOVE 后")
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.2)
    enum_windows("WM_LBUTTONDOWN 后")
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
    time.sleep(1.0)
    enum_windows("WM_LBUTTONUP 后")
    return 0


if __name__ == "__main__":
    sys.exit(main())
