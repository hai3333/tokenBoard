#!/usr/bin/env python3
"""运行态验收：无边框自绘标题栏 + 交互。"""
import ctypes
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

sys.path.insert(0, r"D:\个人资料\项目\token看板")
from tokenboard.ui.win32 import HTCLIENT, HTCAPTION  # noqa: E402

user32 = ctypes.windll.user32
WM_NCHITTEST = 0x0084
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A
SW_RESTORE = 9


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


hwnd = find_window()
if not hwnd:
    print("!! 未找到窗口")
    sys.exit(1)

user32.ShowWindow(hwnd, SW_RESTORE)
time.sleep(1.0)

r = wintypes.RECT()
user32.GetClientRect(hwnd, ctypes.byref(r))
cw, ch = r.right - r.left, r.bottom - r.top
scale = cw / 700.0
print(f"客户区 {cw}x{ch}  缩放 {scale:.3f}  逻辑 {cw/scale:.0f}x{ch/scale:.0f}")

wr = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(wr))
print(f"窗口   {wr.right-wr.left}x{wr.bottom-wr.top} "
      f"(== 客户区? {wr.right-wr.left == cw and wr.bottom-wr.top == ch})")


def hit_test(lx, ly):
    """按客户区逻辑坐标发起一次命中测试。"""
    px = int(lx * scale)
    py = int(ly * scale)
    scr = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(scr))
    lparam = ((scr.y + py) << 16) | ((scr.x + px) & 0xFFFF)
    return user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lparam)


print("\n=== 命中测试 ===")
print(f"  标题栏空白 (100, 15)   -> {hit_test(100, 15)}  "
      f"{'HTCAPTION(可拖动)' if hit_test(100, 15) == HTCAPTION else 'HTCLIENT'}")
print(f"  关闭按钮   (680, 15)   -> {hit_test(680, 15)}  "
      f"{'HTCLIENT(可点)' if hit_test(680, 15) == HTCLIENT else '!! 不可点'}")
print(f"  最小化按钮 (640, 15)   -> {hit_test(640, 15)}  "
      f"{'HTCLIENT(可点)' if hit_test(640, 15) == HTCLIENT else '!! 不可点'}")
print(f"  正文区域   (300, 100)  -> {hit_test(300, 100)}  "
      f"{'HTCLIENT' if hit_test(300, 100) == HTCLIENT else '!! 异常'}")


def click(lx, ly):
    px = int(lx * scale)
    py = int(ly * scale)
    lparam = (py << 16) | (px & 0xFFFF)
    user32.SendMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.1)
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.08)
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
    time.sleep(0.5)


print("\n=== 标题栏按钮点击 ===")
print(f"  点击前 IsWindowVisible={user32.IsWindowVisible(hwnd)}")
click(680, 15)          # 关闭按钮
time.sleep(0.6)
vis = user32.IsWindowVisible(hwnd)
print(f"  点关闭后 IsWindowVisible={vis}  -> {'已收进托盘' if not vis else '!! 仍显示'}")

# 再显示回来
user32.ShowWindow(hwnd, SW_RESTORE)
time.sleep(0.8)
print(f"  恢复后 IsWindowVisible={user32.IsWindowVisible(hwnd)}")

# 最小化按钮
click(640, 15)
time.sleep(0.6)
print(f"  点最小化后 IsWindowVisible={user32.IsWindowVisible(hwnd)} "
      f"IsIconic={user32.IsIconic(hwnd)}")
user32.ShowWindow(hwnd, SW_RESTORE)
time.sleep(0.6)
print("\n验收完毕")
