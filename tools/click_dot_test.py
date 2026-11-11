#!/usr/bin/env python3
"""对运行中的 TokenBoard 真实点击底部状态点（OpenCode），验证跳转+展开。"""
import ctypes
import sys
import time
from ctypes import wintypes

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow" and user32.IsWindowVisible(h):
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            found.append(((r.right - r.left) * (r.bottom - r.top), h))
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


def click(sx, sy):
    user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(1.2)


def main() -> int:
    hwnd = find_window()
    if not hwnd:
        print("!! 没找到窗口")
        return 1
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    scale = (r.right - r.left) / 700.0

    # 客户区原点在标题栏下方，要把客户区坐标换算成屏幕坐标
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    print(f"窗口 ({r.left},{r.top})  客户区原点 ({origin.x},{origin.y})  缩放 {scale:.2f}")

    # 直接给窗口发 WM_LBUTTONDOWN，走的是同一条 WndProc -> on_click 路径，
    # 但不受锁屏/窗口遮挡影响（SendMessage 需要客户区坐标）
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202

    def send_click(design_x, design_y):
        px = int(design_x * scale)
        py = int(design_y * scale)
        lp = (py << 16) | (px & 0xFFFF)
        user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 0, lp)
        user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lp)
        time.sleep(0.6)

    # 状态点在底部：y = BODY_Y + CARD_H + 18 + 12 = 352（客户区设计坐标）
    for name, dx in (("opencode", 229), ("zcode", 321)):
        print(f"点击 {name} 状态点 @ 设计坐标 ({dx + 4}, 359)")
        send_click(dx + 4, 359)
        img = capture(hwnd)
        img.save(rf"D:\个人资料\项目\token看板\tools\ui_dot_{name}.png")
        print(f"  已保存 ui_dot_{name}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
