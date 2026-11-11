#!/usr/bin/env python3
"""校验托盘图标：注册状态 / 屏幕位置 / 左键能否唤起面板。

用法：
    python tools\verify_tray_icon.py            # 校验当前运行的实例
    python tools\verify_tray_icon.py --no-click # 只查注册与位置，不动窗口
"""
from __future__ import annotations

import argparse
import ctypes
import subprocess
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

WM_TRAY = 0x8001
WM_LBUTTONUP = 0x0202


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    """GetRect 专用结构：GUID 必须按 4 字节对齐，cbSize 要填对，
    否则调用会静默返回全零矩形，看起来像「图标没注册」。"""
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", GUID)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def find_window() -> int | None:
    """按窗口类名找 TokenBoard 主窗口（不依赖进程名，exe/源码两种都行）。"""
    hits: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "TokenBoardWindow":
            hits.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return hits[0] if hits else None


def icon_rect(hwnd: int, uid: int = 1):
    q = NOTIFYICONIDENTIFIER()
    q.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
    q.hWnd = hwnd
    q.uID = uid
    r = RECT()
    shell32.Shell_NotifyIconGetRect(ctypes.byref(q), ctypes.byref(r))
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-click", action="store_true", help="不模拟点击")
    args = ap.parse_args()

    hwnd = find_window()
    if not hwnd:
        print("[FAIL] 没找到 TokenBoardWindow，程序没在运行？")
        return 1
    print(f"TokenBoardWindow hwnd = {hwnd}")

    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    notify = user32.FindWindowExW(tray, 0, "TrayNotifyWnd", None) if tray else None
    tray_rect = RECT()
    if notify:
        user32.GetWindowRect(notify, ctypes.byref(tray_rect))

    r = icon_rect(hwnd, 1)
    has = r.right > r.left
    print(f"\n[1] Shell_NotifyIconGetRect -> "
          f"({r.left},{r.top},{r.right},{r.bottom})")
    if not has:
        print("    [FAIL] 图标未注册到通知区域")
        return 1
    print("    [OK] 图标已注册")
    print(f"    通知区域 TrayNotifyWnd rect="
          f"({tray_rect.left},{tray_rect.top},{tray_rect.right},{tray_rect.bottom})")
    if r.top >= sh - 120:
        print(f"    位置：系统托盘**可见区**（任务栏右下角，^ 箭头左侧）")
    elif r.left > sw:
        print("    位置：屏幕外 -> 在「隐藏图标」溢出面板里（面板折叠时坐标在外）")
    else:
        print(f"    位置：其它区域（屏幕 {sw}x{sh}）")

    if args.no_click:
        return 0

    print("\n[2] 模拟托盘左键（发 WM_TRAY + WM_LBUTTONUP）")
    user32.ShowWindow(hwnd, 0)          # 先藏起来，模拟「面板已收进托盘」
    time.sleep(0.4)
    before = bool(user32.IsWindowVisible(hwnd))
    user32.PostMessageW(hwnd, WM_TRAY, 1, WM_LBUTTONUP)
    time.sleep(1.0)
    after = bool(user32.IsWindowVisible(hwnd))
    print(f"    点击前 visible={before} -> 点击后 visible={after}")
    if after:
        print("    [OK] 托盘点击能唤起面板")
        return 0
    print("    [FAIL] 托盘点击没能唤起面板")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
