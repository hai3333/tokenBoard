#!/usr/bin/env python3
"""运行态缩放验收：真实改变窗口尺寸，检查三视图重排是否正确。"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.path.insert(0, r"D:\个人资料\项目\token看板\tools")

user32 = ctypes.windll.user32
OUT = r"D:\个人资料\项目\token看板\tools"

SW_SHOW = 5
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A

TITLE_H = 30
VIEW_SEG_X = 16
VIEW_SEG_W = 54
SEG_Y = TITLE_H + 10
SEG_H = 24


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


def resize(hwnd, logical_w, logical_h, scale=1.5):
    """按逻辑像素改变窗口尺寸。

    跨进程 MoveWindow 是异步的：真正生效要等窗口所属线程处理完消息，
    GetClientRect 会先返回旧值 —— 这里轮询等到尺寸对上再继续。
    """
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
    time.sleep(0.5)


def main():
    from wincap import capture_client

    hwnd = find_window()
    if not hwnd:
        print("!! 未找到窗口")
        return 1
    user32.ShowWindow(hwnd, SW_SHOW)
    time.sleep(1.0)

    # 用窗口的 DPI 算缩放，别拿当前客户区反推（尺寸变了就不准了）
    dpi = user32.GetDpiForWindow(hwnd)
    scale = dpi / 96.0
    print(f"初始客户区 {client_size(hwnd)}  DPI={dpi} 缩放 {scale:.3f}")

    sizes = [(980, 640), (620, 420), (700, 430)]
    for lw, lh in sizes:
        cw, ch = resize(hwnd, lw, lh, scale)
        tag = f"rsz_{lw}x{lh}"
        print(f"\n--- 目标 {lw}x{lh}  实际客户区 {cw}x{ch} ---")

        # 视图一：按工具
        click(hwnd, VIEW_SEG_X + VIEW_SEG_W * 0.5, SEG_Y + SEG_H / 2, scale)
        img = capture_client(hwnd)
        img.save(os.path.join(OUT, f"{tag}_app.png"))
        print(f"  按工具 -> {tag}_app.png {img.size}")

        # 视图三：订阅额度
        click(hwnd, VIEW_SEG_X + VIEW_SEG_W * 2.5, SEG_Y + SEG_H / 2, scale)
        for _ in range(6):
            user32.SendMessageW(hwnd, WM_MOUSEWHEEL, (120 << 16) & 0xFFFFFFFF, 0)
            time.sleep(0.2)
        img = capture_client(hwnd)
        img.save(os.path.join(OUT, f"{tag}_quota.png"))
        print(f"  订阅额度 -> {tag}_quota.png {img.size}")

    print("\n完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
