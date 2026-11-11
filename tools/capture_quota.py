#!/usr/bin/env python3
"""对运行中的 TokenBoard.exe 真实截屏验收「订阅额度」视图。

用 ImageGrab 抓真实屏幕（PrintWindow 对最小化窗口不可靠）。
点击用 SendMessageW 直接发消息，不依赖物理鼠标。
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from PIL import Image, ImageGrab

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x0002, 0x0001, 0x0040
SW_RESTORE = 9
SW_SHOW = 5

# 深色版布局常量（与 tokenboard/ui/panel.py 保持一致）
TITLE_H = 30
VIEW_SEG_X = 16          # PAD
VIEW_SEG_W = 54
SEG_Y = TITLE_H + 10
SEG_H = 24

OUT_DIR = r"D:\个人资料\项目\token看板\tools"


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow":
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), h))
        return True

    user32.EnumWindows(cb, 0)
    found.sort(reverse=True)
    return found[0][1] if found else None


def restore(hwnd):
    """确保窗口是正常显示状态（可能被最小化到托盘了）。"""
    for _ in range(20):
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        if not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, SW_SHOW)      # 隐藏的要用 SW_SHOW
            time.sleep(0.5)
            continue
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.6)
            continue
        if (r.right - r.left) > 400:
            return True
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.4)
    return False


def grab(hwnd, path):
    """窗口自绘内容截图（WM_PRINTCLIENT 路线）。"""
    for _ in range(10):
        restore(hwnd)
        r = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(r))
        if (r.right - r.left) > 400 and (r.bottom - r.top) > 300:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("窗口无法恢复成正常大小")

    from wincap import capture_client
    img = capture_client(hwnd)
    img.save(path)
    return img.size


def click(hwnd, scale, dx, dy):
    lparam = (int(dy * scale) << 16) | (int(dx * scale) & 0xFFFF)
    user32.SendMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.1)
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.08)
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
    time.sleep(0.6)


def main():
    hwnd = find_window()
    if not hwnd:
        print("!! 未找到窗口")
        return 1
    if not restore(hwnd):
        print("!! 窗口无法恢复")
        return 1
    time.sleep(1.5)

    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    scale = (r.right - r.left) / 700.0
    print(f"缩放 {scale:.2f}")

    # 等额度数据回来
    time.sleep(9)

    def click_seg(idx):
        click(hwnd, scale, VIEW_SEG_X + VIEW_SEG_W * (idx + 0.5), SEG_Y + SEG_H / 2)

    # 1) 按工具
    click_seg(0)
    time.sleep(1.0)
    p0 = os.path.join(OUT_DIR, "shot_app.png")
    print("已保存", p0, grab(hwnd, p0))

    # 2) 按模型
    click_seg(1)
    time.sleep(1.0)
    p1 = os.path.join(OUT_DIR, "shot_model.png")
    print("已保存", p1, grab(hwnd, p1))

    # 3) 订阅额度（顶部）
    click_seg(2)
    time.sleep(1.2)
    for _ in range(6):
        user32.SendMessageW(hwnd, WM_MOUSEWHEEL, (120 << 16) & 0xFFFFFFFF, 0)
        time.sleep(0.25)
    time.sleep(0.8)
    p2 = os.path.join(OUT_DIR, "shot_quota_top.png")
    print("已保存", p2, grab(hwnd, p2))

    # 往下滚两格
    for _ in range(2):
        user32.SendMessageW(hwnd, WM_MOUSEWHEEL, (-120 << 16) & 0xFFFFFFFF, 0)
        time.sleep(0.5)
    time.sleep(0.8)
    p3 = os.path.join(OUT_DIR, "shot_quota_scrolled.png")
    print("已保存", p3, grab(hwnd, p3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
