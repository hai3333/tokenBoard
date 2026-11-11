"""列出各显示器的**物理**坐标（DPI 感知），并打印小框当前落在哪。

坑：PowerShell / 普通脚本进程是 DPI-unaware，拿到的屏幕坐标被系统虚拟化过
（2560 的屏会报成 1707），据此判断小框在不在屏内会完全错位。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT,
                                         ctypes.c_void_p, wintypes.UINT]
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_void_p]

MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR,
                                      wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                      wintypes.LPARAM)

ok = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
print("per-monitor-v2:", bool(ok))

print("\n=== 显示器（物理像素）===")
mons = []


def cb(h, _hdc, _lprc, _l):
    r = wintypes.RECT()
    user32.GetMonitorInfoW(h, ctypes.byref(r))
    mons.append((r.left, r.top, r.right, r.bottom))
    return True


user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
for i, (l, t, r, b) in enumerate(mons):
    print(f"  #{i}: ({l},{t}) - ({r},{b})   {r - l}x{b - t}")

wa = wintypes.RECT()
user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)   # SPI_GETWORKAREA
print(f"\n主显示器工作区 SPI_GETWORKAREA: ({wa.left},{wa.top}) - "
      f"({wa.right},{wa.bottom})")

print("\n=== TokenBoard 窗口 ===")
found = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def wcb(h, _l):
    c = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, c, 256)
    if c.value.startswith("TokenBoard"):
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        found.append((c.value, r.left, r.top, r.right, r.bottom))
    return True


user32.EnumWindows(wcb, 0)
for cls, l, t, r, b in found:
    on = [i for i, (ml, mt, mr, mb) in enumerate(mons) if ml <= l and mr >= r]
    where = f"在显示器 {on}" if on else "落在屏幕之间的缝隙里（看不到！）"
    print(f"  {cls:26s} ({l},{t}) - ({r},{b})  {where}")
