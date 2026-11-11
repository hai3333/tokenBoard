#!/usr/bin/env python3
"""边缘光标确定性验证。

锁屏状态下 SetCursorPos 无效（光标根本不动），外部读 GetCursor() 拿到的
又是 Winlogon 桌面的光标，所以「把鼠标挪过去看光标形状」这条路在自动化
环境里验证不了。

这里改成**进程内注入光标位置**：伪造 GetCursorPos 的返回值，让窗口自己
走完 屏幕坐标 -> 客户区坐标 -> 命中测试 -> 光标 ID 这条链路，
直接检查「光标显示能缩放 = 那里真能缩放」。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.config import DB_PATH
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui import win32
from tokenboard.ui.panel import Panel

user32 = ctypes.windll.user32
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

# 注入的光标位置（屏幕坐标）
_fake = [0, 0]


def _fake_get_cursor_pos(lp_point):
    lp_point._obj.x = _fake[0]
    lp_point._obj.y = _fake[1]
    return 1


def main() -> int:
    store = Store(DB_PATH)
    scanner = Scanner(store)
    panel = Panel(store, scanner)
    # 只建窗口，不 start()：避免起定时器/扫描任务，也不会在屏幕上闪一下
    panel.create()

    # 注入点：替换 win32 模块里 user32.GetCursorPos 的取用
    win32.user32.GetCursorPos = _fake_get_cursor_pos

    hwnd = panel.hwnd
    scale = panel.scale
    w, h = panel.width, panel.height
    print(f"窗口 hwnd={hwnd} 逻辑尺寸 {w}x{h} scale={scale}")

    def to_screen(cx_logical, cy_logical):
        """逻辑客户区坐标 -> 屏幕坐标。"""
        pt = wintypes.POINT(int(cx_logical * scale), int(cy_logical * scale))
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    b = panel.resize_border
    cases = [
        ("左上角", b / 2, b / 2, win32.IDC_SIZENWSE),
        ("上边", w / 2, b / 2, win32.IDC_SIZENS),
        ("右上角", w - b / 2, b / 2, win32.IDC_SIZENESW),
        ("左边", b / 2, h / 2, win32.IDC_SIZEWE),
        ("右边", w - b / 2, h / 2, win32.IDC_SIZEWE),
        ("左下角", b / 2, h - b / 2, win32.IDC_SIZENESW),
        ("下边", w / 2, h - b / 2, win32.IDC_SIZENS),
        ("右下角", w - b / 2, h - b / 2, win32.IDC_SIZENWSE),
        ("标题栏空白", 120, 12, win32.IDC_SIZEALL),
        ("正文中间", w / 2, h / 2 + 30, 0),
    ]
    names = {
        win32.IDC_SIZENWSE: "↖↘", win32.IDC_SIZENESW: "↗↙",
        win32.IDC_SIZEWE: "↔", win32.IDC_SIZENS: "↕",
        win32.IDC_SIZEALL: "四向", 0: "默认",
    }
    print("\n边缘光标（注入光标位置，检查窗口算出来的光标 ID）")
    bad = 0
    for name, cx, cy, want in cases:
        sx, sy = to_screen(cx, cy)
        _fake[0], _fake[1] = sx, sy
        got = panel._resize_cursor()
        ht = panel.on_nc_hit_test(cx, cy)
        ok = got == want
        if not ok:
            bad += 1
        print(f"    {name:<12} 客户区({cx:7.1f},{cy:6.1f}) 屏幕({sx},{sy}) "
              f"命中={ht:<3} 光标={names.get(got, got):<4} "
              f"期望={names.get(want, want):<4} {'OK' if ok else '<<< 不对'}")
    print("    ->", "全部正确" if not bad else f"{bad} 处不对")

    # 命中测试与光标必须一致：命中=可缩放的地方，光标就该是缩放箭头
    print("\n一致性：命中可缩放 <-> 光标是缩放箭头")
    inconsistent = 0
    for name, cx, cy, want in cases:
        sx, sy = to_screen(cx, cy)
        _fake[0], _fake[1] = sx, sy
        got = panel._resize_cursor()
        ht = panel.on_nc_hit_test(cx, cy)
        scalable = ht in (win32.HTLEFT, win32.HTRIGHT, win32.HTTOP, win32.HTBOTTOM,
                          win32.HTTOPLEFT, win32.HTTOPRIGHT,
                          win32.HTBOTTOMLEFT, win32.HTBOTTOMRIGHT)
        is_resize_cursor = got in (win32.IDC_SIZEWE, win32.IDC_SIZENS,
                                   win32.IDC_SIZENWSE, win32.IDC_SIZENESW)
        if scalable != is_resize_cursor:
            inconsistent += 1
            print(f"    {name:<12} 命中={ht} 可缩放={scalable} "
                  f"缩放光标={is_resize_cursor}  <<< 不一致")
    print("    ->", "一致" if not inconsistent else f"{inconsistent} 处不一致")

    panel.destroy()
    store.close()
    return 0 if (bad == 0 and inconsistent == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
