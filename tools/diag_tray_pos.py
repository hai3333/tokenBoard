#!/usr/bin/env python3
"""精确判定 TokenBoard 托盘图标在 Win11 通知区域的位置（可见区 / 溢出面板）。

要点：
- NOTIFYICONIDENTIFIER 必须按真实对齐定义（GUID 对齐 4，sizeof=36），
  用 ctypes.c_byte*16 会算成 40，cbSize 错了 GetRect 会静默返回零矩形。
- 拿到 rect 后与屏幕/任务栏/溢出窗口的矩形比对即可判定归属。
"""
from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", GUID)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def main():
    print("sizeof(NOTIFYICONIDENTIFIER) =", ctypes.sizeof(NOTIFYICONIDENTIFIER))

    # 找 TokenBoard 主窗口
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq TokenBoard.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
    pids = {int([p.strip('" ') for p in l.split('","')][1])
            for l in out.splitlines()
            if len([p.strip('" ') for p in l.split('","')]) > 1
            and [p.strip('" ') for p in l.split('","')][1].isdigit()}
    target = None
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        nonlocal target
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value in pids:
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if cls.value == "TokenBoardWindow":
                target = hwnd
    user32.EnumWindows(cb, 0)
    print("TokenBoardWindow hwnd =", target)
    if not target:
        return 1

    for uid in (1, 0):
        nid = NOTIFYICONIDENTIFIER()
        nid.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        nid.hWnd = target
        nid.uID = uid
        r = RECT()
        hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(r))
        if not hr:
            print(f"  uID={uid} -> 未注册 / GetRect 失败")
            continue
        print(f"  uID={uid} -> 已注册 rect=({r.left},{r.top},{r.right},{r.bottom})")

    # 屏幕尺寸
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    print(f"\n屏幕 {sw}x{sh}")

    # 任务栏 / 通知区窗口结构
    def children(parent, depth=0, maxd=4):
        out = []
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def c2(hwnd, _l):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            rr = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rr))
            vis = bool(user32.IsWindowVisible(hwnd))
            out.append((depth, hwnd, cls.value, (rr.left, rr.top, rr.right, rr.bottom), vis))
            if depth < maxd:
                out.extend(children(hwnd, depth + 1, maxd))
            return True
        user32.EnumChildWindows(parent, c2, 0)
        return out

    tray = user32.FindWindowW("Shell_TrayWnd", None)
    print("\n任务栏窗口树 (Shell_TrayWnd):")
    if tray:
        for d, h, cls, rr, vis in children(tray):
            print(f"  {'  '*d}[{cls}] hwnd={h} rect={rr} visible={vis}")

    # 溢出面板
    print("\n顶层窗口里找 NotifyIconOverflowWindow / TrayNotify:")
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def c3(hwnd, _l):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if "NotifyIconOverflow" in cls.value or "TrayNotify" in cls.value:
            rr = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rr))
            print(f"  [{cls.value}] hwnd={hwnd} rect={(rr.left,rr.top,rr.right,rr.bottom)} "
                  f"visible={bool(user32.IsWindowVisible(hwnd))}")
    user32.EnumWindows(c3, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
