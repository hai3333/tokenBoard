"""把小框挪回指定位置（写完等应用自己把位置落盘）。

用法： python tools/place_mini.py 2190 213
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\个人资料\项目\token看板")

user32 = ctypes.windll.user32
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


def find(class_name):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == class_name:
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def main() -> int:
    x, y = int(sys.argv[1]), int(sys.argv[2])
    mins = find("TokenBoardMini")
    if not mins:
        print("没找到小框窗口")
        return 1
    h = mins[0]
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    w, ht = r.right - r.left, r.bottom - r.top
    user32.SetWindowPos(h, None, x, y, w, ht, SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(2.2)          # 等应用的刷新定时器把位置写回 widget.json
    r2 = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r2))
    print(f"小框现在在 {r2.left},{r2.top}（{r2.right - r2.left}x{r2.bottom - r2.top}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
