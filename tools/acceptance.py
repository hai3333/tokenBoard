#!/usr/bin/env python3
"""运行态验收：三种窗口尺寸 × 三个视图，逐一截图，并校验托盘图标。

用法：python tools\\acceptance.py
产物：tools\\acc_<WxH>_<view>.png
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

ROOT = r"D:\个人资料\项目\token看板"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

user32 = ctypes.windll.user32
OUT = os.path.join(ROOT, "tools")

SW_SHOW = 5
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202

TITLE_H = 30
VIEW_SEG_X = 16
VIEW_SEG_W = 54
SEG_Y = TITLE_H + 10
SEG_H = 24

VIEWS = [("app", 0.5), ("model", 1.5), ("quota", 2.5)]


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow":
            found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def client_size(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def resize(hwnd, logical_w, logical_h, scale):
    """跨进程 MoveWindow 是异步的，轮询等到客户区尺寸对上。"""
    want_w, want_h = int(logical_w * scale), int(logical_h * scale)
    user32.MoveWindow(hwnd, 0, 0, want_w, want_h, True)
    for _ in range(40):
        time.sleep(0.15)
        cw, ch = client_size(hwnd)
        if abs(cw - want_w) <= 1 and abs(ch - want_h) <= 1:
            break
    return client_size(hwnd)


def click(hwnd, lx, ly, scale):
    px, py = int(lx * scale), int(ly * scale)
    lparam = (py << 16) | (px & 0xFFFF)
    user32.SendMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.08)
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.06)
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
    time.sleep(0.6)


def ensure_visible(hwnd):
    """抓图前确保窗口是显示状态。

    窗口一旦被收进托盘（隐藏），DWM 就没有重定向表面，
    PrintWindow 抓回来是一张全黑图 —— 之前几张黑图就是这么来的。
    """
    if not user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.UpdateWindow(hwnd)
        time.sleep(0.6)


def main():
    from wincap import capture_client

    hwnd = find_window()
    if not hwnd:
        print("[FAIL] 未找到 TokenBoardWindow")
        return 1
    user32.ShowWindow(hwnd, SW_SHOW)
    time.sleep(1.0)

    dpi = user32.GetDpiForWindow(hwnd)
    scale = dpi / 96.0
    print(f"初始客户区 {client_size(hwnd)}  DPI={dpi}  缩放 {scale:.3f}\n")

    results = []
    for lw, lh in [(980, 640), (700, 430), (620, 420)]:
        cw, ch = resize(hwnd, lw, lh, scale)
        ok_size = (abs(cw - lw * scale) <= 2 and abs(ch - lh * scale) <= 2)
        print(f"--- 目标 {lw}x{lh} -> 客户区 {cw}x{ch} "
              f"{'[OK]' if ok_size else '[尺寸不符]'} ---")
        for name, idx in VIEWS:
            click(hwnd, VIEW_SEG_X + VIEW_SEG_W * idx, SEG_Y + SEG_H / 2, scale)
            time.sleep(1.6)          # 等额度等异步数据落位
            ensure_visible(hwnd)
            img = capture_client(hwnd)
            path = os.path.join(OUT, f"acc_{lw}x{lh}_{name}.png")
            img.save(path)
            print(f"    {name:6s} -> {os.path.basename(path)}  {img.size}")
            results.append((lw, lh, name, img.size))

    print("\n--- 托盘图标 ---")
    from verify_tray_icon import find_window as vfind, icon_rect
    hwnd2 = vfind()
    if hwnd2:
        r = icon_rect(hwnd2, 1)
        print(f"    rect=({r.left},{r.top},{r.right},{r.bottom}) "
              f"-> {'已注册' if r.right > r.left else '未注册'}")
    else:
        print("    未找到窗口")

    print(f"\n共 {len(results)} 张截图 -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
