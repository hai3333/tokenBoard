#!/usr/bin/env python3
"""验证原生托盘图标是否注册成功（Shell_NotifyIconGetRect）。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PIL import ImageGrab

ROOT = r"D:\个人资料\项目\token看板"
OUT = ROOT + r"\tools\tray_icon.png"

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", ctypes.c_byte * 16)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def find_window(pid: int):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid:
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            found.append((hwnd, cls.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "tokenboard.app"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print("pid", proc.pid)
    time.sleep(9)

    wins = find_window(proc.pid)
    print("该进程的窗口:", wins)

    target = None
    for hwnd, cls in wins:
        if "TokenBoardWindow" in cls:
            target = hwnd
            break
    if target is None:
        print("!! 没找到主窗口")
        proc.terminate()
        return 1

    for uid in (1, 0):
        nid = NOTIFYICONIDENTIFIER()
        nid.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        nid.hWnd = target
        nid.uID = uid
        r = RECT()
        hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(r))
        if hr == 0:
            print(f"  uID={uid} -> 未注册")
            continue
        print(f"  uID={uid} -> 已注册! rect=({r.left},{r.top},{r.right},{r.bottom})")
        if r.right > r.left:
            img = ImageGrab.grab(all_screens=True)
            crop = img.crop((max(0, r.left - 8), max(0, r.top - 8),
                             r.right + 8, r.bottom + 8))
            crop = crop.resize((crop.width * 6, crop.height * 6), Image.LANCZOS)
            crop.save(OUT)
            print("  saved", OUT, crop.size)

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
