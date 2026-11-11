#!/usr/bin/env python3
"""用 TokenBoard 自己的 Window 类复现「客户区原点跑到屏幕 (0,0)」。

最小实验（exp_nccalcsize.py）里同样的 NCCALCSIZE 写法是正常的，
所以问题不在 Win32 语义本身，而在应用这一侧还有别的东西在动手。
这里直接用应用的 Window 类跑，再逐项关掉可疑行为定位。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.ui import win32 as W  # noqa: E402

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


def measure(hwnd, tag):
    wr = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    pt = wintypes.POINT(0, 0)
    ok = user32.ClientToScreen(hwnd, ctypes.byref(pt))
    cr = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    off = (pt.x - wr.left, pt.y - wr.top)
    print(f"  {tag:<22} 窗口原点=({wr.left},{wr.top}) 客户区原点=({pt.x},{pt.y}) "
          f"偏移={off} 客户区={cr.right}x{cr.bottom}")
    return off


def run(label, cls, x=200, y=120, show=True, style=W.WS_FIXED,
        ex_style=W.WS_EX_APPWINDOW):
    w = cls("实验", 1000, 660, class_name="ExpWin2", x=x, y=y,
            style=style, ex_style=ex_style)
    w.create()
    print(f"\n[{label}]")
    measure(w.hwnd, "创建后")
    if show:
        user32.ShowWindow(w.hwnd, 5)     # SW_SHOW
        measure(w.hwnd, "显示后")
    user32.DestroyWindow(w.hwnd)
    return w


def main() -> int:
    run("原样（WS_FIXED + WS_EX_APPWINDOW）", W.Window)

    class NoRound(W.Window):
        def _round_corners(self):
            pass

    run("去掉 _round_corners", NoRound)

    class NoDark(W.Window):
        def _enable_dark_titlebar(self):
            pass

    run("去掉 _enable_dark_titlebar", NoDark)

    class Plain(W.Window):
        """纯 WS_POPUP（没有 WS_THICKFRAME）"""
        def __init__(self, *a, **kw):
            kw["style"] = W.WS_PLAIN
            super().__init__(*a, **kw)

    run("WS_POPUP（无边框）", Plain)

    class NoNccalc(W.Window):
        """完全不处理 WM_NCCALCSIZE"""

        def _handle(self, hwnd, msg, wparam, lparam):
            if msg == W.WM_NCCALCSIZE:
                return 0
            return super()._handle(hwnd, msg, wparam, lparam)

    run("不处理 WM_NCCALCSIZE", NoNccalc)

    class WithEdit(W.Window):
        """带一个原生 EDIT 子控件"""

        def create(self):
            super().create()
            self.e = W.Edit(self.hwnd, 100, 100, 200, 40, text="hello")

    run("带 EDIT 子控件", WithEdit)

    class WithEditAfterShow(W.Window):
        """先显示，再加 EDIT 子控件"""

        def create(self):
            super().create()

    w = WithEditAfterShow("实验", 1000, 660, class_name="ExpWin3",
                          x=200, y=120, style=W.WS_FIXED,
                          ex_style=W.WS_EX_APPWINDOW)
    w.create()
    print("\n[先显示再加 EDIT]")
    measure(w.hwnd, "创建后")
    user32.ShowWindow(w.hwnd, 5)
    measure(w.hwnd, "显示后")
    w.e = W.Edit(w.hwnd, 100, 100, 200, 40, text="hello")
    measure(w.hwnd, "加 EDIT 后")
    user32.DestroyWindow(w.hwnd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
