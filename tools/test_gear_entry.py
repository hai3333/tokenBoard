#!/usr/bin/env python3
"""端到端：OpenCode 配置入口必须已经不存在。

需求变化（2026-11-06）：用户说「不要 opencode 配置了」，
所以标题栏齿轮被摘掉，配置窗口不再有任何入口。

本用例反过来断言：
1. 进程里没有 TokenBoardConfigWindow；
2. 点原来齿轮所在的位置，不会弹出任何配置窗口；
3. 点最小化按钮左侧那片「空地」，也不会弹出配置窗口；
4. 面板源码里已经没有 TB_GEAR_X / on_open_config 这些入口残留。

用真实的 WM_LBUTTONDOWN/UP 消息模拟点击（不靠鼠标，锁屏也能测）。
"""
from __future__ import annotations

import ctypes
import os
import re
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.ui.win32 import user32

# 本进程必须 DPI 感知：unaware 时 GetClientRect 返回被虚拟化的尺寸，
# 算出来的点击坐标会偏 440 像素。SetProcessDpiAwarenessContext 失败只返回 FALSE。
_ok = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
if not _ok:
    try:
        _ok = ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
    except Exception:  # noqa: BLE001
        _ok = False
print(f"测试进程 DPI 感知: {_ok}")

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

FAIL = []


def check(name, cond, extra=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


def find_windows(class_name):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == class_name:
            found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found


def click(hwnd, x, y):
    lp = (int(y) << 16) | (int(x) & 0xFFFF)
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.12)
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lp)
    time.sleep(0.8)


def main() -> int:
    print("[1] 源码里没有配置入口残留")
    root = r"D:\个人资料\项目\token看板\tokenboard"
    for name in ("ui/panel.py", "app.py"):
        path = os.path.join(root, name.replace("/", os.sep))
        with open(path, encoding="utf-8") as f:
            src = f.read()
        check(f"{name} 没有 TB_GEAR_X", "TB_GEAR_X" not in src)
        check(f"{name} 没有 on_open_config", "on_open_config" not in src)
        check(f"{name} 没有引用 ConfigWindow", "ConfigWindow" not in src)

    panel = find_windows("TokenBoardWindow")
    if not panel:
        print("[FAIL] 没找到主面板窗口")
        return 1
    hwnd = panel[0]
    dpi = user32.GetDpiForWindow(hwnd)
    scale = dpi / 96.0
    print(f"\n[2] 主面板 hwnd={hwnd} scale={scale}")

    check("初始没有配置窗口", len(find_windows("TokenBoardConfigWindow")) == 0)

    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    win_w = r.right - r.left
    logical_w = win_w / scale
    print(f"客户区 {win_w}x{r.bottom}（设计 {logical_w:.0f} 宽）")

    # 原来齿轮的位置：TB_GEAR_X = WIN_W - 120，按钮宽 40，取中心
    gear_x = int((logical_w - 120 + 20) * scale)
    gear_y = int(15 * scale)
    print(f"点击原齿轮位置：客户区({gear_x},{gear_y})")
    click(hwnd, gear_x, gear_y)
    check("点原齿轮位置不会弹配置窗口",
          len(find_windows("TokenBoardConfigWindow")) == 0)

    # 再点标题栏空白处（搜索框左边那片空白标题栏）：不能弹出任何东西，
    # 也不能顺手把面板收进托盘 —— 坐标要避开最小化/关闭按钮。
    blank_x = int((logical_w - 280) * scale)
    print(f"点击标题栏空白：客户区({blank_x},{gear_y})")
    click(hwnd, blank_x, gear_y)
    check("点空白标题栏不会弹配置窗口",
          len(find_windows("TokenBoardConfigWindow")) == 0)
    check("点空白标题栏不会误关面板", bool(user32.IsWindowVisible(hwnd)))

    print()
    if FAIL:
        print(f"!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
