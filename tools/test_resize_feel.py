#!/usr/bin/env python3
"""缩放手感体检：边缘命中测试 / 最小尺寸钳制 / 光标形状。

三项都过才算缩放真的能用：
1. 四边 + 四角是否返回正确的 HT* （能不能抓住）
2. 缩到比最小尺寸还小时会不会被拦住
3. 鼠标停在边缘时是不是缩放光标（不是默认箭头）
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

user32 = ctypes.windll.user32

WM_NCHITTEST = 0x0084
WM_SETCURSOR = 0x0020
HTCLIENT, HTCAPTION = 1, 2
HTTOP, HTBOTTOM, HTLEFT, HTRIGHT = 12, 15, 10, 11
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17

user32.SendMessageW.restype = ctypes.c_longlong
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 ctypes.c_size_t, ctypes.c_ssize_t]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

IDC = {32642: "IDC_SIZENWSE(↖↘)", 32643: "IDC_SIZENESW(↗↙)",
       32644: "IDC_SIZEWE(↔)", 32645: "IDC_SIZENS(↕)"}


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow":
            found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def hit(hwnd, sx, sy):
    """按屏幕坐标做一次命中测试。"""
    lparam = (sy << 16) | (sx & 0xFFFF)
    return user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lparam)


def client_rect(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def main():
    hwnd = find_window()
    if not hwnd:
        print("[FAIL] 没找到 TokenBoardWindow")
        return 1
    print(f"窗口 hwnd={hwnd}  客户区={client_rect(hwnd)}")

    # ---------- 1) 边缘命中 ----------
    l, t, r, b = window_rect(hwnd)
    cw, ch = client_rect(hwnd)
    dpi = user32.GetDpiForWindow(hwnd)
    scale = dpi / 96.0
    print(f"窗口矩形 = ({l},{t})-({r},{b})  客户区 = {cw}x{ch}  "
          f"DPI={dpi} scale={scale:.3f}")
    print(f"逻辑客户区 = {cw/scale:.1f}x{ch/scale:.1f}")
    cases = [
        ("左上角", l + 2, t + 2, HTTOPLEFT),
        ("上边", (l + r) // 2, t + 2, HTTOP),
        ("右上角", r - 2, t + 2, HTTOPRIGHT),
        ("左边", l + 2, (t + b) // 2, HTLEFT),
        ("右边", r - 2, (t + b) // 2, HTRIGHT),
        ("左下角", l + 2, b - 2, HTBOTTOMLEFT),
        ("下边", (l + r) // 2, b - 2, HTBOTTOM),
        ("右下角", r - 2, b - 2, HTBOTTOMRIGHT),
        ("标题栏空白", l + 300, t + 12, HTCAPTION),
        ("正文中间", (l + r) // 2, (t + b) // 2, HTCLIENT),
    ]
    print("\n[1] 边缘命中测试")
    bad = 0
    for name, sx, sy, want in cases:
        got = hit(hwnd, sx, sy)
        ok = got == want
        if not ok:
            bad += 1
        print(f"    {name:<12} 屏幕({sx},{sy}) 客户区({sx-l},{sy-t}) "
              f"期望 {want:<3} 实际 {got:<3} {'OK' if ok else '<<< 不对'}")
    print("    ->", "全部正确" if not bad else f"{bad} 处不对")

    # ---------- 2) 最小尺寸钳制 ----------
    print("\n[2] 最小尺寸钳制（先放大，再请求缩到比最小值还小）")
    scale = user32.GetDpiForWindow(hwnd) / 96.0
    user32.MoveWindow(hwnd, l, t, int(900 * scale), int(600 * scale), True)
    time.sleep(0.8)
    print(f"    放大到 900x600 -> 实际 {int(client_rect(hwnd)[0]/scale)}x"
          f"{int(client_rect(hwnd)[1]/scale)}")
    for want_logical in (300, 400, 500):
        px_w, px_h = int(want_logical * scale), int(300 * scale)
        user32.MoveWindow(hwnd, l, t, px_w, px_h, True)
        time.sleep(0.7)
        cw, ch = client_rect(hwnd)
        print(f"    请求 {want_logical}x300 -> 实际 {int(cw/scale)}x{int(ch/scale)} "
              f"{'(被钳住)' if cw >= int(620*scale) - 2 else '(没拦住!)'}")

    # 复位
    user32.MoveWindow(hwnd, l, t, int(700 * scale), int(430 * scale), True)
    time.sleep(0.8)
    print(f"    复位 700x430 -> 实际 {int(client_rect(hwnd)[0]/scale)}x"
          f"{int(client_rect(hwnd)[1]/scale)}")

    # ---------- 3) 边缘光标 ----------
    print("\n[3] 边缘光标（把鼠标挪到边缘，检查光标形状是否变成缩放箭头）")
    IDC_ARROW = 32512
    IDC_SIZEWE, IDC_SIZENS = 32644, 32645
    IDC_SIZENWSE, IDC_SIZENESW = 32642, 32643
    user32.SetCursor.argtypes = [wintypes.HANDLE]
    user32.SetCursor.restype = wintypes.HANDLE
    user32.GetCursor.restype = wintypes.HANDLE
    user32.LoadCursorW.restype = wintypes.HANDLE
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]

    def cursor_at(sx, sy):
        user32.SetCursorPos(sx, sy)
        time.sleep(0.15)
        user32.SendMessageW(hwnd, WM_SETCURSOR, hwnd, 0)
        time.sleep(0.15)
        return user32.GetCursor()

    want = {
        "右边": (r - 2, (t + b) // 2, IDC_SIZEWE),
        "下边": ((l + r) // 2, b - 2, IDC_SIZENS),
        "右上角": (r - 2, t + 2, IDC_SIZENESW),
        "正文中间": ((l + r) // 2, (t + b) // 2, IDC_ARROW),
    }
    names = {32512: "箭头", 32644: "↔", 32645: "↕", 32642: "↖↘", 32643: "↗↙"}
    print("    LoadCursorW 句柄对照：")
    for cid, nm in names.items():
        print(f"      IDC {cid} ({nm}) -> {user32.LoadCursorW(None, ctypes.c_void_p(cid))}")
    print(f"      当前 GetCursor() -> {user32.GetCursor()}")
    bad_cursor = 0
    for name, (sx, sy, expect) in want.items():
        cur = cursor_at(sx, sy)
        ref = user32.LoadCursorW(None, ctypes.c_void_p(expect))
        ok = cur == ref
        if not ok:
            bad_cursor += 1
        print(f"    {name:<10} 光标={names.get(cur, cur):<5} 期望={names[expect]:<5} "
              f"{'OK' if ok else '<<< 不对'}")
    print("    ->", "全部正确" if not bad_cursor else f"{bad_cursor} 处不对")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
