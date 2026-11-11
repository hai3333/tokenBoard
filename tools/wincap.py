#!/usr/bin/env python3
"""窗口截图：跨进程抓取自绘窗口。

路线选择（踩过的坑，勿轻易改）：
* **不能用 WM_PRINTCLIENT 跨进程传 DC** —— GDI 的 DC 是进程私有的，
  对端拿到一个不属于自己进程的句柄，BitBlt 会静默失败，截出来是一张全黑图。
  （同进程内 WM_PRINTCLIENT 是好的。）
* **PrintWindow(hwnd, mem, 2)** 走 DWM 的重定向表面，跨进程可用。
  标志位必须用 PW_RENDERFULLCONTENT(2)；用 0(PW_CLIENTONLY) 会让系统把
  WM_PRINTCLIENT 发给对端进程，又回到上面那个坑。
* 位图尺寸要按**客户区**（= 窗口区，无边框窗口两者相等），
  按 GetWindowRect 会出现内容偏移、边缘发白。
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# 抓图进程自己必须是 DPI 感知的（踩过的坑）：
# 144dpi 机器上，unaware 进程调 GetClientRect 拿到的是被系统虚拟化过的
# 尺寸（物理 1320 -> 虚拟 880）。拿这个尺寸建位图去抓 1320x780 的窗口，
# 内容就被压成 2/3，看着像「界面缩成一小块」，其实是抓图工具的锅。
# 必须在任何窗口尺寸查询之前切换。
def _enable_dpi_awareness() -> bool:
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        return bool(user32.SetProcessDPIAware())
    except Exception:  # noqa: BLE001
        return False


DPI_AWARE = _enable_dpi_awareness()

# 句柄在 64 位下可能超过 32 位，不设原型会被截断/符号扩展
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int,
                                         ctypes.c_int]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT,
                             wintypes.UINT, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

PW_RENDERFULLCONTENT = 0x00000002


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def capture_client(hwnd):
    """返回客户区位图（PIL Image，RGB）。"""
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise RuntimeError("客户区尺寸异常")

    hdc = user32.GetWindowDC(hwnd)
    try:
        # GDI 句柄只有低 32 位有效，ctypes 会把返回值符号扩展成
        # 0xFFFFFFFFxxxxxxxx，掩掉高位再往下传。
        mem = gdi32.CreateCompatibleDC(hdc) & 0xFFFFFFFF
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mem, bmp)
        # 必须用 PW_RENDERFULLCONTENT(2)：走 DWM 重定向表面，跨进程可用
        user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
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
        img = img.convert("RGB")
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        return img
    finally:
        user32.ReleaseDC(hwnd, hdc)
