#!/usr/bin/env python3
"""跑一遍三种 WM_NCCALCSIZE 写法，看配置窗口的客户区原点分别落在哪。

背景：配置窗口建在 (200,120)，但客户区原点跑到了屏幕 (0,0)，
界面左上角被裁掉一块（部署版截图里 provider 名字和标题栏都没了）。
本脚本给应用进程注入 TB_NCCALC_MODE 环境变量，分别测 none/r0/all。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
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
ROOT = r"D:\个人资料\项目\token看板"


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


def measure(h):
    wr = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(wr))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(pt))
    return (wr.left, wr.top), (pt.x, pt.y)


def run_mode(mode):
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { "
         "$_.CommandLine -like '*tokenboard.app*' } | ForEach-Object { "
         "Stop-Process -Id $_.ProcessId -Force }"], capture_output=True)
    time.sleep(2.5)
    env = dict(os.environ)
    env["TOKENBOARD_TRACE"] = "1"
    env["TB_NCCALC_MODE"] = mode
    subprocess.Popen([r"D:\software\anaconda3\python.exe", "-m", "tokenboard.app"],
                     cwd=ROOT, env=env)
    panel = None
    for _ in range(40):
        time.sleep(0.5)
        w = finds("TokenBoardWindow")
        if w:
            panel = w[0]
            break
    if not panel:
        print(f"[{mode}] 没找到主面板")
        return
    lp = (22 << 16) | (1170 & 0xFFFF)
    user32.SendMessageW(panel, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.15)
    user32.SendMessageW(panel, WM_LBUTTONUP, 0, lp)
    time.sleep(2.5)
    cws = finds("TokenBoardConfigWindow")
    if not cws:
        print(f"[{mode}] 配置窗口没出来")
        return
    w0, c0 = measure(cws[0])
    # 再点一次（reload + show 的二次路径）
    user32.SendMessageW(panel, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.15)
    user32.SendMessageW(panel, WM_LBUTTONUP, 0, lp)
    time.sleep(2.0)
    cws = finds("TokenBoardConfigWindow")
    w1, c1 = measure(cws[0])
    ok = "OK " if c1 == w1 else "!! "
    print(f"{ok}TB_NCCALC_MODE={mode:<5} 首次: 窗口原点={w0} 客户区原点={c0} | "
          f"二次: 窗口原点={w1} 客户区原点={c1}")


if __name__ == "__main__":
    modes = sys.argv[1:] or ["none", "r0", "all", "screen", "keep"]
    for m in modes:
        run_mode(m)
