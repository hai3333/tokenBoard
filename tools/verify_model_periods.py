#!/usr/bin/env python3
"""真实交互验证：对运行中的 TokenBoard.exe 切换模型视图的时间范围并截图。"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200

# 界面设计坐标
WIN_W = 700
WIN_H = 400
PAD = 16
HEADER_Y = 16
VIEW_SEG_W = 54
VIEW_SEG_H = 22
VIEW_SEG_Y = HEADER_Y + 26
VIEW_SEG_X = PAD + 152

SEG_W = 58
SEG_H = 26
SEG_Y = 18
SEG_X = WIN_W - PAD - SEG_W * 4


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
        if c.value == "TokenBoardWindow" and user32.IsWindowVisible(h):
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            area = (r.right - r.left) * (r.bottom - r.top)
            found.append((area, h))
        return True

    user32.EnumWindows(cb, 0)
    found.sort(reverse=True)
    return found[0][1] if found else None


def capture(hwnd) -> Image.Image:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)
    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return img


def click_client(hwnd, scale, dx, dy):
    """给窗口发送客户区点击消息（dx, dy 为设计坐标）。"""
    # 考虑标题栏和边框偏移，直接用 SendMessageW 发 WM_LBUTTONDOWN/UP 给客户区
    cx = int(dx * scale)
    cy = int(dy * scale)
    lparam = (cy << 16) | (cx & 0xFFFF)
    user32.SendMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 0x0001, lparam)
    time.sleep(0.05)
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
    time.sleep(0.3)


def main():
    hwnd = find_window()
    if not hwnd:
        print("!! 未找到 TokenBoard 窗口")
        return 1
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(1)

    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    cw, ch = r.right - r.left, r.bottom - r.top
    scale = cw / 700.0
    print(f"客户区尺寸 {cw}x{ch}  缩放比 {scale:.2f}")

    out_dir = r"D:\个人资料\项目\token看板\tools"

    # 1. 点击切换到「按模型」视图（第 2 个 tab）
    print("-> 点击切换到「按模型」视图...")
    click_client(hwnd, scale, VIEW_SEG_X + VIEW_SEG_W * 1.5, VIEW_SEG_Y + VIEW_SEG_H / 2)
    time.sleep(0.5)

    # 2. 依次点击「今天」、「7 天」、「30 天」、「全部」
    periods = [("today", 0), ("7d", 1), ("30d", 2), ("all", 3)]
    for name, idx in periods:
        px = SEG_X + idx * SEG_W + SEG_W / 2
        py = SEG_Y + SEG_H / 2
        print(f"-> 点击时间范围 [{name}] ({px}, {py})...")
        click_client(hwnd, scale, px, py)
        time.sleep(0.5)
        img = capture(hwnd)
        p = os.path.join(out_dir, f"shot_model_{name}.png")
        img.save(p)
        print(f"   已保存截图 {p}")

    # 3. 点击切换到「订阅额度」视图（第 3 个 tab）
    print("-> 点击切换到「订阅额度」视图...")
    click_client(hwnd, scale, VIEW_SEG_X + VIEW_SEG_W * 2.5, VIEW_SEG_Y + VIEW_SEG_H / 2)
    time.sleep(1.2)
    img_quota = capture(hwnd)
    pq = os.path.join(out_dir, "shot_quota.png")
    img_quota.save(pq)
    print(f"   已保存订阅额度截图 {pq}")

    # 4. 切回「按工具」
    click_client(hwnd, scale, VIEW_SEG_X + VIEW_SEG_W * 0.5, VIEW_SEG_Y + VIEW_SEG_H / 2)
    print("全部测试点击与截图完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
