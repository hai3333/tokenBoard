#!/usr/bin/env python3
"""验证滚轮：发真实的 WM_MOUSEWHEEL 消息（向上/向下），检查滚动位置。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"D:\个人资料\项目\token看板"
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
VK_DOWN, VK_END = 0x28, 0x23


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
    print(f"      [窗口矩形] {r.left},{r.top} - {r.right},{r.bottom}  {w}x{h}"
          f"  visible={user32.IsWindowVisible(hwnd)}")
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


def wheel(hwnd, delta, x=400, y=300):
    wp = ((delta & 0xFFFF) << 16)
    lp = (y << 16) | (x & 0xFFFF)
    user32.SendMessageW(hwnd, WM_MOUSEWHEEL, wp, lp)
    time.sleep(0.35)


def main() -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "TOKENBOARD_VIEW": "model", "TOKENBOARD_PERIOD": "all",
           "TOKENBOARD_TRACE": "1"}
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(2)
    proc = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT, env=env)
    time.sleep(13)
    hwnd = find_window()
    if not hwnd:
        print("!! 没找到窗口")
        proc.terminate()
        return 1
    # 万一被最小化了（点到标题栏的最小化按钮），先还原
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        time.sleep(0.6)
    print("窗口已找到，开始发滚轮消息")

    capture(hwnd).save(rf"{ROOT}\tools\wheel_0.png")
    print("  初始 -> wheel_0.png")

    for i in range(3):
        wheel(hwnd, 120)      # 向上滚
    capture(hwnd).save(rf"{ROOT}\tools\wheel_up3.png")
    print("  上滚 3 格 -> wheel_up3.png")

    for i in range(3):
        wheel(hwnd, -120)     # 向下滚
    capture(hwnd).save(rf"{ROOT}\tools\wheel_down3.png")
    print("  下滚 3 格 -> wheel_down3.png")

    for i in range(10):
        wheel(hwnd, -120)
    capture(hwnd).save(rf"{ROOT}\tools\wheel_down13.png")
    print("  再下滚 10 格 -> wheel_down13.png")

    user32.SendMessageW(hwnd, WM_KEYDOWN, VK_END, 0)
    time.sleep(0.4)
    capture(hwnd).save(rf"{ROOT}\tools\wheel_end.png")
    print("  End 键 -> wheel_end.png")

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
