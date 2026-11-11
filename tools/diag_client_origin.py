#!/usr/bin/env python3
"""重测：配置窗口客户区原点 vs 窗口原点，以及 EDIT 的真实相对位置。

上一次测量可能假阳性：MapWindowPoints / ClientToScreen 失败时 POINT 不会被修改，
拿没变化的点当结果就等于什么都没测。这次每个调用都检查返回值。
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

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.MapWindowPoints.restype = ctypes.c_int
user32.MapWindowPoints.argtypes = [wintypes.HWND, wintypes.HWND,
                                   ctypes.POINTER(wintypes.POINT), ctypes.c_uint]
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202


def find_windows(class_name, pids=None):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == class_name:
            if pids is None:
                out.append(h)
            else:
                p = wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                if p.value in pids:
                    out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def live_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process TokenBoard -ErrorAction SilentlyContinue).Id"],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return {int(x) for x in out.split() if x.strip().isdigit()}


def client_origin(hwnd):
    pt = wintypes.POINT(0, 0)
    ok = user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y), bool(ok)


def child_map(parent):
    """返回 [(edit hwnd, 屏幕矩形, 相对父客户区的矩形)]，带返回值。"""
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, c, 64)
        if c.value == "Edit":
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            p = wintypes.POINT(r.left, r.top)
            ok = user32.MapWindowPoints(parent, None, ctypes.byref(p), 1)
            out.append((h, (r.left, r.top, r.right - r.left, r.bottom - r.top),
                        (p.x, p.y), bool(ok), user32.GetParent(h) == parent))
        return True

    user32.EnumChildWindows(parent, cb, 0)
    return out


def report(cw, tag):
    wr = wintypes.RECT()
    user32.GetWindowRect(cw, ctypes.byref(wr))
    cr = wintypes.RECT()
    user32.GetClientRect(cw, ctypes.byref(cr))
    org, ok = client_origin(cw)
    print(f"\n[{tag}]")
    print(f"  窗口矩形   = ({wr.left},{wr.top})-({wr.right},{wr.bottom})  "
          f"{wr.right-wr.left}x{wr.bottom-wr.top}")
    print(f"  客户区大小 = {cr.right}x{cr.bottom}")
    print(f"  客户区原点 = {org}  (ClientToScreen 成功={ok})")
    print(f"  偏移       = 客户区原点 - 窗口原点 = "
          f"({org[0]-wr.left},{org[1]-wr.top})")
    for h, s, rel, ok2, ischild in child_map(cw):
        print(f"  edit {h:<10} 屏幕{s} -> 相对父客户区 {rel} "
              f"(映射成功={ok2}, 是子窗口={ischild})")


def main() -> int:
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(3.5)
    subprocess.Popen([r"D:\software\TokenBoard\TokenBoard.exe"],
                     cwd=r"D:\software\TokenBoard")
    time.sleep(3.0)
    pids = live_pids()
    panel = None
    for _ in range(40):
        time.sleep(0.5)
        w = find_windows("TokenBoardWindow", pids)
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

    cws = find_windows("TokenBoardConfigWindow", pids)
    if not cws:
        print("配置窗口没出来")
        return 1
    cw = cws[0]
    report(cw, "配置窗口")

    print("\n主面板对照:")
    report(panel, "主面板")

    mins = find_windows("TokenBoardMini", pids)
    for m in mins:
        report(m, "桌面小框")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
