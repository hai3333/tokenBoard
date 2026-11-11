#!/usr/bin/env python3
"""源码级探针：缩放窗口时看 WM_SIZE / 画布有没有跟上。"""
import ctypes
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui.panel import Panel
from tokenboard.ui.win32 import user32

ensure_dirs()
store = Store(DB_PATH)
panel = Panel(store, Scanner(store))
panel.create()
panel.show()
time.sleep(0.5)

MSG = ctypes.wintypes.MSG if hasattr(ctypes, "wintypes") else None


def pump(seconds=1.0):
    end = time.time() + seconds
    msg = ctypes.wintypes.MSG()
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)


def client():
    r = wintypes.RECT()
    user32.GetClientRect(panel.hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


pump(0.5)
print(f"初始  client={client()}  panel.width={panel.width} height={panel.height}")
c = panel._canvas
print(f"       canvas={c}  canvas 尺寸={c.w}x{c.h} 物理={int(c.w*c.scale)}x{int(c.h*c.scale)}")

for target in ((1470, 960), (930, 630)):
    user32.MoveWindow(panel.hwnd, 0, 0, target[0], target[1], True)
    pump(1.0)
    c = panel._canvas
    print(f"缩到 {target}: client={client()}  panel.width={panel.width} "
          f"height={panel.height}  canvas={c.w}x{c.h} 物理={int(c.w*c.scale)}x{int(c.h*c.scale)}")

panel.destroy()
