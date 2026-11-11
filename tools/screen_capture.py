"""抓**屏幕区域**（不是窗口表面），看半透明窗口叠在桌面上是什么效果。

PrintWindow 抓的是窗口自己的像素，看不出 alpha 混合后的样子；
要验证「透不透」必须从屏幕 DC 上按坐标抠那一块。

用法：
    python tools/screen_capture.py                # 抓小框所在区域
    python tools/screen_capture.py --class TokenBoardWindow
"""
from __future__ import annotations

import argparse
import ctypes
import sys
from ctypes import wintypes

sys.path.insert(0, r"D:\个人资料\项目\token看板")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                         wintypes.DWORD]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                             wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
                             wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

SRCCOPY = 0x00CC0020


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


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


def grab(x, y, w, h, out_path):
    screen = user32.GetDC(None)
    try:
        mem = gdi32.CreateCompatibleDC(screen)
        bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
        gdi32.SelectObject(mem, bmp)
        gdi32.BitBlt(mem, 0, 0, w, h, screen, x, y, SRCCOPY)
        bi = BIH()
        bi.biSize = ctypes.sizeof(BIH)
        bi.biWidth = w
        bi.biHeight = -h
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
        from PIL import Image
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        img.convert("RGB").save(out_path)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        return img.size
    finally:
        user32.ReleaseDC(None, screen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class", dest="cls", default="TokenBoardMini")
    ap.add_argument("--out", default=r"D:\个人资料\项目\token看板\tools\screen_mini.png")
    ap.add_argument("--pad", type=int, default=40)
    args = ap.parse_args()

    ok = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    print("per-monitor-v2:", bool(ok))

    wins = find(args.cls)
    if not wins:
        print(f"没找到 {args.cls}")
        return 1
    h = wins[0]
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    x, y = r.left, r.top
    w, hh = r.right - r.left, r.bottom - r.top
    p = args.pad
    x = max(0, x - p)
    y = max(0, y - p)
    size = grab(x, y, w + p * 2, hh + p * 2, args.out)
    print(f"{args.cls} 窗口在 ({r.left},{r.top}) {w}x{hh}  -> {args.out} {size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
