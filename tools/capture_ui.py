#!/usr/bin/env python3
"""可靠截图：把窗口临时置顶 + 鼠标挪开，然后截真实屏幕。

（PrintWindow 走 WM_PRINT，而本程序只在 WM_PAINT 里自绘，截出来是旧帧。）
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PIL import ImageGrab

ROOT = r"D:\个人资料\项目\token看板"
OUT = ROOT + r"\tools\ui_shot_win.png"

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x0002, 0x0001, 0x0040
SW_RESTORE = 9


def find_window(pid):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        if not user32.IsWindowVisible(h):
            return True
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value != pid:
            return True
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow":
            found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def main() -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for k in ("TOKENBOARD_VIEW", "TOKENBOARD_PERIOD", "TOKENBOARD_EXPAND"):
        if k in os.environ:
            env[k] = os.environ[k]
    proc = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT, env=env)
    print("pid", proc.pid)

    hwnd = None
    for _ in range(40):
        time.sleep(0.5)
        hwnd = find_window(proc.pid)
        if hwnd:
            break
    if not hwnd:
        print("!! 没找到窗口")
        proc.terminate()
        return 1

    time.sleep(12)
    # 鼠标挪开，别停在标题栏按钮上
    user32.SetCursorPos(20, 700)
    time.sleep(0.5)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.8)
    # 临时置顶，保证截到的是它
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.2)

    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    print("rect", r.left, r.top, r.right, r.bottom)
    img = ImageGrab.grab(all_screens=True)
    crop = img.crop((r.left, r.top, r.right, r.bottom))
    crop.save(OUT)
    print("saved", OUT, crop.size)

    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
