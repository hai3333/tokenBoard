#!/usr/bin/env python3
"""验收：主面板 / 配置窗口 / 桌面小框，三个窗口的客户区原点都要等于窗口原点。

背景：WM_NCCALCSIZE 里写窗口坐标会让客户区被钉到屏幕 (0,0)，
配置窗口（建在 200,120）的左上角会被裁掉一块。

用法：python tools/check_client_origin.py [面板hwnd来源]
   默认测量**当前已经在跑**的 TokenBoard（源码版或 exe 版都行），
   并顺手点开配置窗口一起量。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                wintypes.LPARAM]

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
FAIL = []


def finds(cn):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == cn:
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def check_window(cn, expect_min=1):
    wins = finds(cn)
    if not wins:
        print(f"  FAIL 找不到 {cn}")
        FAIL.append(cn)
        return
    for h in wins:
        wr = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(wr))
        pt = wintypes.POINT(0, 0)
        ok = bool(user32.ClientToScreen(h, ctypes.byref(pt)))
        off = (pt.x - wr.left, pt.y - wr.top)
        good = off == (0, 0)
        print(f"  {'OK  ' if good else 'FAIL'} {cn:<22} hwnd={h:<10} "
              f"窗口原点=({wr.left},{wr.top}) 客户区原点=({pt.x},{pt.y}) 偏移={off}")
        if not good:
            FAIL.append(f"{cn} 偏移{off}")
        if not ok:
            print("       (ClientToScreen 调用失败)")


def main() -> int:
    panels = finds("TokenBoardWindow")
    if not panels:
        print("没找到主面板，先把 TokenBoard 跑起来")
        return 1
    panel = panels[0]

    # 点齿轮开配置窗口
    lp = (22 << 16) | (1170 & 0xFFFF)
    user32.SendMessageW(panel, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.15)
    user32.SendMessageW(panel, WM_LBUTTONUP, 0, lp)
    time.sleep(2.0)

    print("客户区原点验收：")
    check_window("TokenBoardWindow")
    check_window("TokenBoardConfigWindow")
    check_window("TokenBoardMini")

    print()
    if FAIL:
        print(f"!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
