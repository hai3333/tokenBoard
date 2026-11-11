#!/usr/bin/env python3
"""反复缩放窗口，看内存/GDI 资源有没有泄漏。

画布是按窗口尺寸分配的 DIB，每次 on_size 都会 close 掉重建。
如果 close 漏了或没置空，反复缩放就会越吃越多内存。
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND,
                                                    wintypes.LPARAM), wintypes.LPARAM]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetGuiResources.argtypes = [wintypes.HANDLE, ctypes.c_uint]
user32.GetGuiResources.restype = ctypes.c_uint


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


def pid_of(hwnd):
    p = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


def mem_of(pid):
    """返回 (工作集MB, GDI对象数, USER对象数)。"""
    import subprocess
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$p=Get-Process -Id " + str(pid) + "; "
         "[math]::Round($p.WorkingSet64/1MB,2)"],
        capture_output=True, text=True)
    try:
        ws = float(out.stdout.strip() or 0)
    except ValueError:
        ws = 0.0
    h = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
    gdi = user32.GetGuiResources(h, 0) if h else 0
    usr = user32.GetGuiResources(h, 1) if h else 0
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
    return ws, gdi, usr


def main():
    hwnd = find_window()
    if not hwnd:
        print("[FAIL] 未找到 TokenBoardWindow")
        return 1
    pid = pid_of(hwnd)
    dpi = user32.GetDpiForWindow(hwnd)
    scale = dpi / 96.0
    print(f"hwnd={hwnd} pid={pid} scale={scale}")

    sizes = [(980, 640), (700, 430), (620, 420), (900, 600)]
    # 先热身：跑一轮，让首帧画布/GDI 对象建好
    for lw, lh in sizes:
        user32.MoveWindow(hwnd, 0, 0, int(lw * scale), int(lh * scale), True)
        time.sleep(0.4)
    time.sleep(1.5)
    base = mem_of(pid)
    print(f"热身结束: 工作集={base[0]:.2f}MB GDI对象={base[1]} USER对象={base[2]}")

    for rnd in range(1, 6):
        for lw, lh in sizes:
            user32.MoveWindow(hwnd, 0, 0, int(lw * scale), int(lh * scale), True)
            time.sleep(0.25)
        time.sleep(1.2)
        ws, gdi, usr = mem_of(pid)
        print(f"  第{rnd}轮缩放后: 工作集={ws:.2f}MB "
              f"({'+' if ws - base[0] >= 0 else ''}{ws - base[0]:.2f}) "
              f"GDI对象={gdi}({'+' if gdi - base[1] >= 0 else ''}{gdi - base[1]}) "
              f"USER对象={usr}({'+' if usr - base[2] >= 0 else ''}{usr - base[2]})")

    # 复位到默认尺寸
    user32.MoveWindow(hwnd, 0, 0, int(700 * scale), int(430 * scale), True)
    time.sleep(1.0)
    ws, gdi, usr = mem_of(pid)
    print(f"复位后: 工作集={ws:.2f}MB GDI对象={gdi} USER对象={usr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
