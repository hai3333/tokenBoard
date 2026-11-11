#!/usr/bin/env python3
"""抓取展开下钻状态的界面（按工具 / 按模型 各一张），用 PrintWindow 直接渲染窗口。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image

ROOT = Path(r"D:\个人资料\项目\token看板")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass


class BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


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


def shoot(view: str, expand: str, period: str, out: str):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "TOKENBOARD_VIEW": view, "TOKENBOARD_EXPAND": expand,
           "TOKENBOARD_PERIOD": period}
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(2)
    proc = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=str(ROOT),
                            env=env)
    time.sleep(13)
    wins = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow" and user32.IsWindowVisible(h):
            rr = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(rr))
            area = (rr.right - rr.left) * (rr.bottom - rr.top)
            wins.append((area, h))
        return True

    user32.EnumWindows(cb, 0)
    if not wins:
        print(f"{out}: 没找到窗口")
        proc.terminate()
        return
    wins.sort(reverse=True)
    print(f"  候选窗口: {[(a, h) for a, h in wins]}")
    img = capture(wins[0][1])
    img.save(str(ROOT / "tools" / out))
    print(f"{out}: 已保存 {img.size}")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()


if __name__ == "__main__":
    shoot("app", "opencode", "all", "ui_shot_expand_app.png")
    time.sleep(2)
    shoot("model", "deepseek-v4.1-flash", "all", "ui_shot_expand_model.png")
