"""验小框的悬停态（真鼠标版）。

为什么不能用合成 WM_NCMOUSEMOVE：那条路会立刻招来一个
WM_NCMOUSELEAVE（真鼠标根本不在窗口上，系统当场发「已离开」），
悬停态刚开就被关掉，看起来像功能没生效。

做法：把真鼠标挪到小框中间 -> 等 -> 抓屏幕 -> 挪回去。
挪不动（有人在同时用电脑）就 SKIP，不算失败。

用法： python tools/test_mini_hover.py
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.path.insert(0, r"D:\个人资料\项目\token看板\tools")

from screen_capture import grab  # noqa: E402

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

OUT = r"D:\个人资料\项目\token看板\tools"
FAIL = []
SKIP = []


def check(name, cond, extra=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


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


def cursor():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def goto(x, y, tries=12):
    for _ in range(tries):
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.06)
        cx, cy = cursor()
        if abs(cx - x) <= 2 and abs(cy - y) <= 2:
            return True
    return False


def shot(x, y, w, h, name):
    grab(x, y, w, h, f"{OUT}\\{name}.png")
    from PIL import Image
    return Image.open(f"{OUT}\\{name}.png").convert("RGB")


def main() -> int:
    print("per-monitor-v2:",
          bool(user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))))
    mins = find("TokenBoardMini")
    if not mins:
        print("[FAIL] 没找到 TokenBoardMini")
        return 1
    h = mins[0]
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    x, y = r.left, r.top
    w, hh = r.right - r.left, r.bottom - r.top
    scale = user32.GetDpiForWindow(h) / 96.0
    print(f"小框 hwnd={h} 位置=({x},{y}) {w}x{hh} scale={scale}")

    orig = cursor()
    tx, ty = x + int(120 * scale), y + int(30 * scale)

    print("\n[1] 鼠标移开 -> 基线画面")
    if not goto(tx, ty + 400):
        print("  SKIP 鼠标挪不动（有人在同时用电脑）")
        SKIP.append("真鼠标悬停")
    else:
        time.sleep(0.6)
        base = shot(x, y, w, hh, "hover_0_base")
        print("\n[2] 鼠标移上去 -> 应该出现悬停态（top3 速览）")
        if not goto(tx, ty):
            print("  SKIP 鼠标挪不动")
            SKIP.append("真鼠标悬停")
        else:
            time.sleep(0.8)
            hot = shot(x, y, w, hh, "hover_1_hot")
            diff = sum(1 for a, b in zip(base.getdata(), hot.getdata()) if a != b)
            check("悬停画面变了", diff > 200, f"差异像素 {diff}")
            print("\n[3] 鼠标移开 -> 悬停态应该消失")
            goto(tx, ty + 400)
            time.sleep(0.8)
            back = shot(x, y, w, hh, "hover_2_back")
            diff2 = sum(1 for a, b in zip(base.getdata(), back.getdata()) if a != b)
            check("画面还原了", diff2 < 200, f"差异像素 {diff2}")

    goto(orig[0], orig[1])
    print(f"  鼠标已挪回 {cursor()}")

    if FAIL:
        print(f"\n!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    if SKIP:
        print(f"\n全部通过（跳过：{SKIP}）")
        return 0
    print("\n全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
