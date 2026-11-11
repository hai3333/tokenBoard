"""量一下原生 EDIT 在当前 DPI 下的自然高度（单行）。

为什么要量：
单行 EDIT 的高度是系统按字体算出来的（CreateWindowExW 传的高度会被改掉），
配置窗要把输入框放在自绘的圆角「井」里垂直居中，
不量就不知道该给多高，只能瞎猜 —— 猜小了字被裁，猜大了字浮在上面。

用法： python tools/probe_edit_h.py
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR,
                                    wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                    wintypes.HINSTANCE, wintypes.LPVOID]
user32.GetClientRect.argtypes = [wintypes.HWND,
                                 ctypes.POINTER(wintypes.RECT)]
user32.SendMessageW.restype = ctypes.c_longlong
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                ctypes.c_size_t, ctypes.c_size_t]

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
ES_AUTOHSCROLL = 0x0080
ES_MULTILINE = 0x0004
WM_SETFONT = 0x0030
WM_GETMINMAXINFO = 0x0024


class MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", wintypes.POINT), ("ptMaxSize", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT), ("ptMinTrackSize", wintypes.POINT),
                ("ptMaxTrackSize", wintypes.POINT)]


class TEXTMETRIC(ctypes.Structure):
    _fields_ = [
        ("tmHeight", ctypes.c_long), ("tmAscent", ctypes.c_long),
        ("tmDescent", ctypes.c_long), ("tmInternalLeading", ctypes.c_long),
        ("tmExternalLeading", ctypes.c_long), ("tmAveCharWidth", ctypes.c_long),
        ("tmMaxCharWidth", ctypes.c_long), ("tmWeight", ctypes.c_long),
        ("tmOverhang", ctypes.c_long), ("tmDigitizedAspectX", ctypes.c_long),
        ("tmDigitizedAspectY", ctypes.c_long), ("tmFirstChar", wintypes.WCHAR),
        ("tmLastChar", wintypes.WCHAR), ("tmDefaultChar", wintypes.WCHAR),
        ("tmBreakChar", wintypes.WCHAR), ("tmItalic", ctypes.c_byte),
        ("tmUnderlined", ctypes.c_byte), ("tmStruckOut", ctypes.c_byte),
        ("tmPitchAndFamily", ctypes.c_byte), ("tmCharSet", ctypes.c_byte),
    ]


gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.GetTextMetricsW.argtypes = [wintypes.HDC, ctypes.POINTER(TEXTMETRIC)]


def font_metrics(font_h: int) -> tuple[int, int]:
    fh = make_font(font_h)
    dc = gdi32.CreateCompatibleDC(None)
    gdi32.SelectObject(dc, fh)
    tm = TEXTMETRIC()
    gdi32.GetTextMetricsW(dc, ctypes.byref(tm))
    gdi32.DeleteDC(dc)
    return tm.tmHeight, tm.tmExternalLeading


def make_font(height_px: int, weight: int = 400,
              name: str = "Microsoft YaHei UI") -> int:
    return gdi32.CreateFontW(
        -int(abs(height_px)), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 0, 5, 0, name)


def main() -> None:
    hinst = kernel32.GetModuleHandleW(None)
    parent = user32.CreateWindowExW(0, "STATIC", "probe",
                                     WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                     0, 0, 400, 200, None, None, hinst, None)
    print("parent hwnd =", parent)

    for label, font_h, style, create_h in (
        ("单行 YaHei 10px@1.5 (15物理) h=0", 15, ES_AUTOHSCROLL, 0),
        ("单行 YaHei 10px@1.5 (15物理) h=10", 15, ES_AUTOHSCROLL, 10),
        ("单行 YaHei 9px @1.5 (13物理) h=0", 13, ES_AUTOHSCROLL, 0),
        ("多行 YaHei 9px @1.5 (13物理) h=0", 13, ES_MULTILINE, 0),
    ):
        hwnd = user32.CreateWindowExW(
            0, "EDIT", "", WS_CHILD | WS_VISIBLE | WS_TABSTOP | style,
            0, 0, 200, create_h, parent, None, hinst, None)
        fh = make_font(font_h)
        user32.SendMessageW(hwnd, WM_SETFONT, fh, 1)
        rc = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rc))
        ch = rc.bottom - rc.top
        mmi = MINMAXINFO()
        ptr = ctypes.cast(ctypes.byref(mmi), ctypes.c_void_p).value
        user32.SendMessageW(hwnd, WM_GETMINMAXINFO, 0, ptr)
        th, el = font_metrics(font_h)
        print(f"{label:34s} create_h={create_h:3d} -> client_h={ch:3d}  "
              f"min_track={mmi.ptMinTrackSize.y:3d}  tmHeight={th} extLead={el}")
        user32.DestroyWindow(hwnd)
    user32.DestroyWindow(parent)


if __name__ == "__main__":
    main()
