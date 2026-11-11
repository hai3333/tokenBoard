"""诊断：分层窗口（半透明）到底能不能被「屏幕截图」抓到最新画面。

现象：发了 WM_NCMOUSEMOVE 之后 trace 里确实有 WM_PAINT，
但屏幕区域截图和之前一模一样 —— 怀疑抓的是**旧画面**。

对比三份：
  A 屏幕 BitBlt（未悬停）
  B 屏幕 BitBlt（悬停后）
  C PrintWindow（让窗口自己重画一遍，跨进程可用）
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.path.insert(0, r"D:\个人资料\项目\token看板\tools")

from screen_capture import grab  # noqa: E402
from wincap import capture_client  # noqa: E402

user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                ctypes.c_size_t, ctypes.c_size_t]

WM_NCMOUSEMOVE = 0x00A0
OUT = r"D:\个人资料\项目\token看板\tools"


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


def main() -> int:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    h = find("TokenBoardMini")[0]
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    x, y = r.left, r.top
    w, hh = r.right - r.left, r.bottom - r.top
    scale = user32.GetDpiForWindow(h) / 96.0

    a = grab(x, y, w, hh, f"{OUT}\\diag_A_screen_before.png")
    lp = ((y + int(30 * scale)) << 16) | ((x + int(120 * scale)) & 0xFFFF)
    user32.SendMessageW(h, WM_NCMOUSEMOVE, 0, lp)
    time.sleep(0.8)
    b = grab(x, y, w, hh, f"{OUT}\\diag_B_screen_after.png")
    c = capture_client(h)
    c.save(f"{OUT}\\diag_C_printwindow.png")

    from PIL import Image
    a = Image.open(f"{OUT}\\diag_A_screen_before.png").convert("RGB")
    b = Image.open(f"{OUT}\\diag_B_screen_after.png").convert("RGB")
    da = sum(1 for p, q in zip(a.getdata(), b.getdata()) if p != q)
    print(f"屏幕截图  悬停前 vs 悬停后 差异像素 = {da}")
    print(f"屏幕截图尺寸 {a.size}   PrintWindow 尺寸 {c.size}")
    print("A=diag_A_screen_before  B=diag_B_screen_after  C=diag_C_printwindow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
