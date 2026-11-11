#!/usr/bin/env python3
"""抓取当前正在运行的 TokenBoard 窗口。"""
import ctypes
import sys
from ctypes import wintypes

from PIL import ImageGrab

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

wins = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def cb(h, _l):
    c = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, c, 256)
    if c.value == "TokenBoardWindow" and user32.IsWindowVisible(h):
        wins.append(h)
    return True


user32.EnumWindows(cb, 0)
print(f"找到 {len(wins)} 个窗口")
if wins:
    r = wintypes.RECT()
    user32.GetWindowRect(wins[0], ctypes.byref(r))
    img = ImageGrab.grab(all_screens=True)
    crop = img.crop((r.left, r.top, r.right, r.bottom))
    out = r"D:\个人资料\项目\token看板\tools\ui_shot_win.png"
    crop.save(out)
    print("saved", out, crop.size)
