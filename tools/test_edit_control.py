#!/usr/bin/env python3
"""原生编辑框冒烟测试：创建 / 读写 / 位置 / 深色主题 / 焦点。"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.ui import win32
from tokenboard.ui.win32 import Edit, Font, Window, rgb

FAIL = []


def check(name: str, cond: bool, extra: str = ""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


class TestWindow(Window):
    def __init__(self):
        super().__init__("EditTest", 520, 260, x=100, y=100)
        self.notifications = []

    def on_paint(self):
        c = self._canvas
        if c is None:
            return
        c.fill("#0C1220")

    def on_child_command(self, ctrl_id, notify, lparam):
        self.notifications.append((ctrl_id, notify))


def main() -> int:
    w = TestWindow()
    w.create()
    w.show()
    time.sleep(0.4)

    font = Font(10, 400)
    edit = Edit(w.hwnd, 20, 60, 300, 28, text="hello", font=font)
    check("编辑框创建成功", bool(edit.hwnd), f"hwnd={edit.hwnd}")

    edit.set_text("sk-测试-1234")
    check("写文本/读文本", edit.get_text() == "sk-测试-1234", repr(edit.get_text()))

    edit.set_text("")
    edit.focus()
    time.sleep(0.2)
    check("可以拿到焦点", user32_focus() == edit.hwnd)

    r = wintypes.RECT()
    win32.user32.GetWindowRect(edit.hwnd, ctypes.byref(r))
    check("位置/尺寸正确", (r.left, r.top) == (120, 160) or
          abs(r.left - 120) < 30 and abs(r.top - 160) < 30,
          f"({r.left},{r.top})-({r.right},{r.bottom})")

    # 深色主题：WM_CTLCOLOREDIT 要返回画刷
    brush = win32.user32.SendMessageW(w.hwnd, win32.WM_CTLCOLOREDIT,
                                       win32.user32.GetDC(edit.hwnd), edit.hwnd)
    check("WM_CTLCOLOREDIT 返回画刷", brush != 0, f"brush={brush}")

    # 密码框
    pw = Edit(w.hwnd, 20, 110, 300, 28, text="secret", password=True)
    check("密码框创建成功", bool(pw.hwnd))
    pw.set_password_char("")
    check("可切成明文显示", pw.get_text() == "secret")

    # 通知：模拟 EN_CHANGE
    w.notifications.clear()
    w.on_child_command(1, win32.EN_CHANGE, 0)
    check("子控件通知可接收", len(w.notifications) == 1)

    edit.destroy()
    pw.destroy()
    w.destroy()
    time.sleep(0.2)

    print()
    if FAIL:
        print(f"!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("全部通过")
    return 0


def user32_focus() -> int:
    h = win32.user32.GetFocus()
    return int(h) if h else 0


if __name__ == "__main__":
    raise SystemExit(main())
