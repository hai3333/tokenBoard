#!/usr/bin/env python3
"""诊断 TokenBoard 托盘图标在 Windows 11 通知区域的状态。

回答三个问题：
1. 图标有没有真的注册到 Explorer（Shell_NotifyIconGetRect）。
2. Explorer 认为它在「可见区」还是「隐藏图标」溢出面板（注册表
   HKCU\\Control Panel\\NotifyIconSettings 的 IsPromoted）。
3. 可见托盘区（Shell_TrayWnd 下 ToolbarWindow32）里现在有哪些图标。
"""
from __future__ import annotations

import ctypes
import winreg
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

EXE = r"D:\software\TokenBoard\TokenBoard.exe"


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", ctypes.c_byte * 16)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def enum_proc(cb):
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, lparam):
        cb(hwnd, lparam)
        return True
    return _cb


def find_tokenboard_window():
    """按进程名找到 TokenBoard 的主窗口。"""
    import subprocess
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq TokenBoard.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore").stdout
    pids = []
    for line in out.splitlines():
        parts = [p.strip('" ') for p in line.split('","')]
        if len(parts) > 1 and parts[1].isdigit():
            pids.append(int(parts[1]))
    hits = []
    for pid in pids:
        def _cb(hwnd, _l, pid=pid):
            wpid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value != pid:
                return
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            if "TokenBoard" in cls.value:
                hits.append((hwnd, cls.value, pid))
        user32.EnumWindows(enum_proc(_cb), 0)
    return hits


def toolbar_icons():
    """读可见托盘区 ToolbarWindow32 里的图标个数。"""
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    if not tray:
        return None
    notify = user32.FindWindowExW(tray, 0, "TrayNotifyWnd", None)
    if not notify:
        return None
    pager = user32.FindWindowExW(notify, 0, "SysPager", None)
    if not pager:
        return None
    tb = user32.FindWindowExW(pager, 0, "ToolbarWindow32", None)
    if not tb:
        return None
    TB_BUTTONCOUNT = 0x0418
    cnt = user32.SendMessageW(tb, TB_BUTTONCOUNT, 0, 0)
    return cnt, tb


def overflow_window():
    """Win11 的「隐藏图标」溢出面板窗口（存在但默认折叠）。"""
    found = []
    def _cb(hwnd, _l):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if "NotifyIconOverflowWindow" in cls.value:
            r = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append((hwnd, cls.value, (r.left, r.top, r.right, r.bottom),
                          bool(user32.IsWindowVisible(hwnd))))
    user32.EnumWindows(enum_proc(_cb), 0)
    return found


def registry_state():
    root = r"Control Panel\NotifyIconSettings"
    rows = []
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, root)
    except OSError as e:
        return [("打开失败", str(e))]
    with key:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            info = {}
            try:
                with winreg.OpenKey(key, sub) as sk:
                    for name in ("ExecutablePath", "IsPromoted", "InitialTooltip"):
                        try:
                            info[name] = winreg.QueryValueEx(sk, name)[0]
                        except OSError:
                            pass
            except OSError:
                continue
            rows.append((sub, info))
    return rows


def main():
    print("=" * 78)
    print("1) 托盘图标注册状态")
    wins = find_tokenboard_window()
    print("   TokenBoard 窗口:", [(h, c) for h, c, _ in wins] or "未找到进程")
    for hwnd, cls, _pid in wins:
        for uid in (1, 0):
            nid = NOTIFYICONIDENTIFIER()
            nid.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
            nid.hWnd = hwnd
            nid.uID = uid
            r = RECT()
            hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(r))
            if hr:
                print(f"   hwnd={hwnd} uID={uid} -> 已注册 rect="
                      f"({r.left},{r.top},{r.right},{r.bottom})")

    print()
    print("2) 可见托盘区图标数 / 溢出面板窗口")
    tb = toolbar_icons()
    print("   可见区 toolbar 图标数:", tb[0] if tb else "未找到")
    for hwnd, cls, rect, vis in overflow_window():
        print(f"   溢出面板窗口 hwnd={hwnd} visible={vis} rect={rect}")

    print()
    print("3) 注册表 NotifyIconSettings（IsPromoted=1 可见区 / 0 溢出面板）")
    rows = registry_state()
    tb_rows = [r for r in rows if "tokenboard" in str(r[1]).lower()]
    print(f"   总条目 {len(rows)}，TokenBoard 相关 {len(tb_rows)}")
    for sub, info in tb_rows:
        print(f"   [{sub}] {info}")
    if not tb_rows:
        print("   （未找到 TokenBoard 条目；下面打印前 8 条样例以确认键结构）")
        for sub, info in rows[:8]:
            print(f"   [{sub}] {info}")
    print("=" * 78)


if __name__ == "__main__":
    main()
