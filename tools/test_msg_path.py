"""验证 WM_RBUTTONUP / WM_CHAR 经消息循环真正到达 Panel。"""
from __future__ import annotations

import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tokenboard.config import DB_PATH  # noqa: E402
from tokenboard.pricing import get_pricing  # noqa: E402
from tokenboard.scanner import Scanner  # noqa: E402
from tokenboard.store import Store  # noqa: E402
from tokenboard.ui import panel as P  # noqa: E402
from tokenboard.ui.win32 import MSG, user32  # noqa: E402

WM_RBUTTONUP = 0x0205
WM_CHAR = 0x0102


def pump(ms: int) -> None:
    msg = MSG()
    end = time.time() + ms / 1000
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)


def main() -> int:
    store = Store(DB_PATH)
    store.load_pricing(get_pricing().pricing_map())
    scanner = Scanner(store)
    p = P.Panel(store, scanner)
    p.create()
    p.show()
    pump(1200)

    ok = True

    # 1) 找一个主行的屏幕逻辑坐标，发 WM_RBUTTONUP（lparam = y<<16 | x，按 scale）
    i = next(i for i, r in enumerate(p._rows) if r["kind"] not in ("sub", "ssub"))
    rx, ry, rw, rh = p._row_rect(i)
    lx, ly = int((rx + 30) * p.scale), int((ry + rh / 2) * p.scale)
    lparam = (ly << 16) | (lx & 0xFFFF)
    user32.PostMessageW(p.hwnd, WM_RBUTTONUP, 0, lparam)
    pump(400)
    print("menu items after WM_RBUTTONUP:", [m for m, _ in p._ctx_items])
    ok &= bool(p._ctx_items)

    # 2) WM_CHAR 输入到搜索框
    p._ctx_items = []
    rect = p._search_rect()
    p._search_focus = True
    pump(100)
    for ch in "opencode":
        user32.PostMessageW(p.hwnd, WM_CHAR, ord(ch), 0)
        pump(30)
    print("search_q after WM_CHAR:", p._search_q)
    ok &= p._search_q == "opencode"

    # 3) 非聚焦时 WM_CHAR 不写入
    p._search_focus = False
    p._search_q = ""
    pump(50)
    user32.PostMessageW(p.hwnd, WM_CHAR, ord("q"), 0)
    pump(100)
    print("search_q while unfocused:", repr(p._search_q))
    ok &= p._search_q == ""

    p.destroy()
    print("MSG PATH OK" if ok else "MSG PATH FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
