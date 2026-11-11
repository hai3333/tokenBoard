#!/usr/bin/env python3
"""DPI 感知探针：确认「界面缩成一小块」到底出在应用侧还是抓图工具侧。

关键点：**必须先** SetProcessDpiAwarenessContext，再做任何窗口尺寸查询。
抓图脚本自己若是 DPI-unaware，GetClientRect 拿到的是被系统虚拟化过的
坐标（144dpi 机器上物理 1320 -> 虚拟 880），再拿这个尺寸去建位图抓
1320x780 的窗口，内容就被压成 2/3 —— 看着像「界面缩成一小块」。

用法：
    python tools/dpi_probe.py                 # 只打印状态
    python tools/dpi_probe.py --shot out.png  # 顺带抓一张客户区截图
"""
from __future__ import annotations

import argparse
import ctypes
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = ctypes.c_uint
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
user32.GetWindowDpiAwarenessContext.argtypes = [wintypes.HWND]
user32.GetWindowDpiAwarenessContext.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
PER_MONITOR_V2 = ctypes.c_void_p(-4)

AWARE = {0: "DPI_AWARENESS_UNAWARE",
         1: "DPI_AWARENESS_SYSTEM_AWARE",
         2: "DPI_AWARENESS_PER_MONITOR_AWARE"}


def make_aware() -> bool:
    """把本进程切到 per-monitor v2（必须在建窗口前调用）。"""
    return bool(user32.SetProcessDpiAwarenessContext(PER_MONITOR_V2))


def find_windows(class_names: list[str]) -> list[int]:
    out: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value in class_names:
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", help="同时把客户区截图存到该路径")
    ap.add_argument("--classes", default="TokenBoardWindow",
                    help="要查的窗口类名，逗号分隔")
    args = ap.parse_args()

    aware = make_aware()
    print(f"本进程切到 per-monitor-v2: {aware}")

    names = [n.strip() for n in args.classes.split(",") if n.strip()]
    hw = find_windows(names)
    if not hw:
        print("没找到窗口: " + ", ".join(names))
        return 1

    for h in hw:
        cr = wintypes.RECT()
        user32.GetClientRect(h, ctypes.byref(cr))
        wr = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(wr))
        dpi = user32.GetDpiForWindow(h)
        ctx = user32.GetWindowDpiAwarenessContext(h)
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        print(f"\n[{c.value}] hwnd={h}")
        print(f"  客户区       = {cr.right}x{cr.bottom} 物理像素")
        print(f"  窗口矩形     = {wr.right - wr.left}x{wr.bottom - wr.top}")
        print(f"  GetDpiForWindow = {dpi}")
        print(f"  窗口感知上下文 = {ctx} ({AWARE.get(ctx, ctx)})")
        print(f"  可见        = {bool(user32.IsWindowVisible(h))}")

        if args.shot:
            sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
            from wincap import capture_client
            img = capture_client(h)
            img.save(args.shot)
            print(f"  截图        = {args.shot}  {img.size[0]}x{img.size[1]} 像素")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
