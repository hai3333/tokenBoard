#!/usr/bin/env python3
"""量一下配置窗口里原生 EDIT 子控件到底相对父窗口在哪儿。

怀疑点：EDIT 的位置可能是按**屏幕坐标**摆的（窗口后来被移动/定位后，
子控件就错位了）—— 父窗口自绘内容在右边，编辑框却飘到左上角。
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

# 跨进程发鼠标消息时，系统会按**发送方**的感知状态缩放坐标：
# 发送方 DPI-unaware + 目标 144dpi -> 坐标被乘 0.667，点齿轮就点空了。
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.MapWindowPoints.argtypes = [wintypes.HWND, wintypes.HWND,
                                   ctypes.POINTER(wintypes.POINT), ctypes.c_uint]
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]

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
    """当前存活的 TokenBoard.exe 进程 PID 集合（onefile 会有父子两个）。"""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process TokenBoard -ErrorAction SilentlyContinue).Id"],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return {int(x) for x in out.split() if x.strip().isdigit()}


def child_edits(parent):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, c, 64)
        if c.value == "Edit":
            out.append(h)
        return True

    user32.EnumChildWindows(parent, cb, 0)
    return out


def report(cw, tag):
    wr = wintypes.RECT()
    user32.GetWindowRect(cw, ctypes.byref(wr))
    org = wintypes.POINT(0, 0)
    user32.ClientToScreen(cw, ctypes.byref(org))
    print(f"\n[{tag}] 父窗口屏幕 ({wr.left},{wr.top})，客户区原点屏幕 ({org.x},{org.y})")
    for h in child_edits(cw):
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        p = wintypes.POINT(r.left, r.top)
        user32.MapWindowPoints(cw, None, ctypes.byref(p), 1)
        print(f"  edit hwnd={h:<10} 屏幕({r.left},{r.top}) "
              f"相对父客户区=({p.x},{p.y}) "
              f"父={user32.GetParent(h)==cw} 尺寸={r.right-r.left}x{r.bottom-r.top}")


def main() -> int:
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(3.5)
    subprocess.Popen([r"D:\software\TokenBoard\TokenBoard.exe"],
                     cwd=r"D:\software\TokenBoard")
    time.sleep(3.0)
    pids = live_pids()
    print("存活的 TokenBoard.exe PID:", pids)
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
    print("点击后存活 PID:", live_pids())
    print("所有 TokenBoardConfigWindow:",
          find_windows("TokenBoardConfigWindow"))
    log = Path.home() / "AppData/Local/TokenBoard/tokenboard.log"
    if log.exists():
        print("--- 日志尾部 ---")
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]:
            print("  " + line)
    if not cws:
        print("配置窗口没出来")
        return 1
    cw = cws[0]
    report(cw, "刚打开")

    # 把窗口挪 200,120，看子控件跟不跟着走
    wr = wintypes.RECT()
    user32.GetWindowRect(cw, ctypes.byref(wr))
    user32.SetWindowPos(cw, None, wr.left + 200, wr.top + 120, 0, 0,
                        0x0001 | 0x0004)      # SWP_NOSIZE | SWP_NOZORDER
    time.sleep(0.8)
    report(cw, "整体右移 200 下移 120 之后")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
