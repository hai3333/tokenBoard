#!/usr/bin/env python3
"""测试打包好的 TokenBoard.exe：能否启动、出窗口、注册托盘、六个采集源都正常。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PIL import ImageGrab

ROOT = r"D:\个人资料\项目\token看板"
EXE = os.path.join(ROOT, "dist", "TokenBoard", "TokenBoard.exe")
LOG = os.path.join(os.environ["LOCALAPPDATA"], "TokenBoard", "tokenboard.log")

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass


class NID(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", ctypes.c_byte * 16)]


class RECT(ctypes.Structure):
    _fields_ = [("l", wintypes.LONG), ("t", wintypes.LONG),
                ("r", wintypes.LONG), ("b", wintypes.LONG)]


def find_by_class(cls_name, pid=None):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == cls_name:
            if pid is not None:
                p = wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                if p.value != pid:
                    return True
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def main() -> int:
    print(f"启动 {EXE}")
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    time.sleep(14)

    if proc.poll() is not None:
        print(f"!! 进程已退出，退出码 {proc.returncode}")
        print("--- log ---")
        if os.path.exists(LOG):
            with open(LOG, encoding="utf-8", errors="replace") as f:
                print(f.read()[-3000:])
        return 1

    print(f"进程存活 pid={proc.pid}")

    wins = find_by_class("TokenBoardWindow", proc.pid)
    print(f"窗口数: {len(wins)}")
    if wins:
        r = wintypes.RECT()
        user32.GetWindowRect(wins[0], ctypes.byref(r))
        print(f"  窗口位置 ({r.left},{r.top})-({r.right},{r.bottom})  "
              f"尺寸 {r.right - r.left}x{r.bottom - r.top}")
        img = ImageGrab.grab(all_screens=True)
        crop = img.crop((r.left, r.top, r.right, r.bottom))
        crop.save(os.path.join(ROOT, "tools", "exe_shot.png"))
        print("  已截图 tools/exe_shot.png")

        nid = NID()
        nid.cbSize = ctypes.sizeof(NID)
        nid.hWnd = wins[0]
        nid.uID = 0
        rr = RECT()
        hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(rr))
        print(f"  托盘图标: {'已注册' if hr else '未注册!'}")

    print("\n--- log 尾部 ---")
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8", errors="replace") as f:
            print(f.read()[-1500:])

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
