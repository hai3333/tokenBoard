"""确定性验证：拖动结束消息 0x0232 -> 位置立刻落盘。

为什么要单独一个用例：test_mini.py 里这一步排在「真实鼠标拖拽」后面。
有人同时用这台电脑时，真拖拽会把窗口留在系统的模态移动状态里，
后面再用 SetWindowPos 挪位置会被移动循环覆盖掉，于是断言读到的坐标对不上
—— 那是环境干扰，不是功能坏了。

这里不碰真鼠标：直接 SetWindowPos 到一个已知坐标 -> 删掉状态文件 ->
PostMessage(0x0232) -> 读文件，必须正好是刚设的那个坐标。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.config import WIDGET_STATE_PATH  # noqa: E402
from tokenboard.ui.win32 import user32  # noqa: E402

_ok = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
if not _ok:
    try:
        _ok = ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
    except Exception:  # noqa: BLE001
        _ok = False
print(f"测试进程 DPI 感知: {bool(_ok)}")

WM_EXITSIZEMOVE = 0x0232
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

FAIL = []


def check(name, cond, extra=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


def find_mini():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "TokenBoardMini":
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out[0] if out else None


def win_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def main() -> int:
    mini = find_mini()
    if not mini:
        print("[FAIL] 没找到小框窗口")
        return 1

    r = win_rect(mini)
    w, h = r.right - r.left, r.bottom - r.top
    nx, ny = 1800, 700
    print(f"小框 hwnd={mini} 当前 {r.left},{r.top} {w}x{h}")

    user32.SetWindowPos(mini, None, nx, ny, w, h,
                        SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.4)
    r2 = win_rect(mini)
    check("已挪到指定坐标", (r2.left, r2.top) == (nx, ny),
          f"{r2.left},{r2.top}（期望 {nx},{ny}）")
    check("尺寸没变", (r2.right - r2.left, r2.bottom - r2.top) == (w, h))

    try:
        os.remove(WIDGET_STATE_PATH)
    except Exception:  # noqa: BLE001
        pass
    check("状态文件已删除（确保下面是消息驱动的写入）",
          not os.path.exists(WIDGET_STATE_PATH))

    user32.PostMessageW(mini, WM_EXITSIZEMOVE, 0, 0)
    time.sleep(0.40)          # 远小于刷新定时器(1.5s)，只可能是消息驱动的写入
    saved = {}
    try:
        with open(WIDGET_STATE_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except Exception:  # noqa: BLE001
        pass
    check("收到 0x0232 后位置立刻落盘",
          saved.get("x") == nx and saved.get("y") == ny,
          f"{saved} vs 期望 x={nx} y={ny}")

    print()
    if FAIL:
        print(f"!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
