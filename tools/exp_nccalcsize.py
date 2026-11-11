#!/usr/bin/env python3
"""最小实验：WM_NCCALCSIZE 各种写法下，客户区原点到底落在哪。

现象（TokenBoard 实测）：WS_POPUP|WS_THICKFRAME 的窗口建在 (200,120)，
但客户区原点跑到屏幕 (0,0) —— 界面左上角被裁掉一块。

这里把几种常见的 NCCALCSIZE 写法各建一个窗口，逐个量：
    窗口原点 vs 客户区原点（ClientToScreen(0,0)）
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32.CreateWindowExW.restype = wintypes.HWND
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.RegisterClassW.argtypes = [ctypes.c_void_p]

WS_POPUP = 0x80000000
WS_THICKFRAME = 0x00040000
WS_VISIBLE = 0x10000000

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("ppos", ctypes.c_void_p)]


class WINDOWPOS(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND),
        ("x", ctypes.c_int), ("y", ctypes.c_int),
        ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", wintypes.UINT),
    ]


WM_NCCALCSIZE = 0x0083
WM_NCCREATE = 0x0081
WM_DESTROY = 0x0002

# 每个变体：返回 (要写哪些 rgrc, 返回值)
VARIANTS = {
    "A 只改 rgrc[0] + return TRUE": ("r0", True),
    "B rgrc[0]+[1]+[2] + return TRUE": ("r012", True),
    "C 只改 rgrc[0] + return FALSE": ("r0", False),
    "D 完全不处理": (None, None),
    "E rgrc[0]=rgrc[1] + return TRUE": ("copy", True),
}


def make_wndproc(mode, ret):
    def proc(hwnd, msg, wparam, lparam):
        if msg == WM_NCCALCSIZE and wparam:
            params = ctypes.cast(lparam, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
            wr = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(wr))
            w = wr.right - wr.left
            h = wr.bottom - wr.top
            ox, oy = wr.left, wr.top
            if params.ppos:
                pos = ctypes.cast(params.ppos, ctypes.POINTER(WINDOWPOS)).contents
                ox, oy = pos.x, pos.y
                if pos.cx and pos.cy:
                    w, h = pos.cx, pos.cy
            if mode == "copy":
                params.rgrc[0] = params.rgrc[1]
            else:
                params.rgrc[0].left = 0
                params.rgrc[0].top = 0
                params.rgrc[0].right = w
                params.rgrc[0].bottom = h
                if mode == "r012":
                    params.rgrc[1].left = ox
                    params.rgrc[1].top = oy
                    params.rgrc[1].right = ox + w
                    params.rgrc[1].bottom = oy + h
                    params.rgrc[2] = params.rgrc[1]
            return 1 if ret else 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    return proc


def main() -> int:
    hinst = kernel32.GetModuleHandleW(None)
    print(f"{'写法':<34} {'窗口原点':<14} {'客户区原点':<14} 偏移")
    for i, (name, (mode, ret)) in enumerate(VARIANTS.items()):
        cls = f"ExpCls{i}"
        proc = make_wndproc(mode, ret)
        wc = WNDCLASS()
        wc.lpfnWndProc = WNDPROC(proc)
        wc.hInstance = hinst
        wc.lpszClassName = cls
        user32.RegisterClassW(ctypes.byref(wc))
        hwnd = user32.CreateWindowExW(
            0, cls, "exp", WS_POPUP | WS_THICKFRAME,
            200, 120, 600, 400, None, None, hinst, None)
        if not hwnd:
            print(f"{name:<34} 创建失败")
            continue

        def measure(tag):
            wr = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(wr))
            pt = wintypes.POINT(0, 0)
            ok = user32.ClientToScreen(hwnd, ctypes.byref(pt))
            cr = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(cr))
            off = (pt.x - wr.left, pt.y - wr.top)
            mark = "OK " if off == (0, 0) else "!! "
            print(f"{mark}{tag:<12}{name:<32} 窗口原点=({wr.left},{wr.top}) "
                  f"客户区原点=({pt.x},{pt.y}) 偏移={off} "
                  f"客户区={cr.right}x{cr.bottom}")
            return off

        measure("隐藏时")
        user32.ShowWindow(hwnd, 5)          # SW_SHOW
        measure("SW_SHOW后")
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE  <- 会再触发一次 NCCALCSIZE
        measure("SW_RESTORE后")
        user32.DestroyWindow(hwnd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
