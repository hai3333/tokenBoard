#!/usr/bin/env python3
"""真实窗口上的「新增 / 删除」按钮点得动吗？

为什么单独测：这两个按钮早前只算了位置、只处理点击，**从来没被画出来**
（画笔调用漏了），用户在界面上根本没法加/删 provider。
光看截图不够，得真的点一下，看库里的 provider 数有没有变。
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.ui.win32 import user32  # noqa: E402

user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
FAIL = []


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


def click(h, x, y):
    lp = (int(y) << 16) | (int(x) & 0xFFFF)
    user32.SendMessageW(h, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.12)
    user32.SendMessageW(h, WM_LBUTTONUP, 0, lp)
    time.sleep(0.5)


def provider_ids():
    from tokenboard.config import DB_PATH
    from tokenboard.providers import ProviderStore
    from tokenboard.store import Store
    s = Store(DB_PATH)
    try:
        return [p.id for p in ProviderStore(s).list()]
    finally:
        s.close()


def main() -> int:
    wins = find("TokenBoardConfigWindow")
    if not wins:
        print("[FAIL] 没找到配置窗口")
        return 1
    h = wins[0]
    dpi = user32.GetDpiForWindow(h)
    sc = dpi / 96.0
    print(f"配置窗口 hwnd={h} dpi={dpi} scale={sc}")

    before = provider_ids()
    print(f"\n[1] 点「新增」")
    print(f"  点之前库里有 {len(before)} 个: {before}")
    # 按钮位置跟着 configwin 的布局常量算：btn_add = (16, list_y+list_h+8)
    PAD, TITLE_H, BAR_H, BTN_H = 16, 34, 40, 28
    list_h = 500 - TITLE_H - PAD - BAR_H - PAD - BTN_H - 8
    list_y = TITLE_H + PAD
    bx, by = 16, list_y + list_h + 8
    click(h, (bx + 34) * sc, (by + BTN_H / 2) * sc)
    after = provider_ids()
    print(f"  点之后库里有 {len(after)} 个: {after}")
    check("点「新增」后多了一个 provider", len(after) == len(before) + 1,
          f"{len(before)} -> {len(after)}")

    print("\n[2] 点「删除」")
    dx, dy = 16 + 74, by
    click(h, (dx + 34) * sc, (dy + BTN_H / 2) * sc)
    back = provider_ids()
    print(f"  点之后库里有 {len(back)} 个: {back}")
    check("点「删除」后又删掉了", len(back) == len(before),
          f"{len(after)} -> {len(back)}")
    check("provider 集合和原来一致", set(back) == set(before),
          f"{sorted(back)} vs {sorted(before)}")

    print()
    if FAIL:
        print(f"!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
