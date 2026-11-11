"""把主面板的四个视图各抓一张图（看配色是否统一）。

用法：python tools/capture_views.py

两个坑：
* **不能在这个进程里创建窗口再存图** —— 这台机器上装了透明加密，
  凡是由「创建了窗口的进程」写出的图片都会变成不可读文件。
  这里只做「抓图方」：找窗口、按键切视图、从**屏幕 DC** 抠像素。
* **PrintWindow 会抓到黑图**（窗口被别的程序盖住时 DWM 重定向表面是空的），
  所以走屏幕 DC，并且先把面板提到前台 —— 抓完会校验左上角是不是面板底色，
  不是就重新提一次（有人在同时用电脑时微信会弹到前面）。
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import screen_capture  # noqa: E402
from tokenboard.ui.win32 import user32  # noqa: E402

# 抓图进程必须自己 DPI 感知：否则 GetWindowRect 返回虚拟坐标（880x520），
# 抠出来的只是面板左上角一块。
_ok = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
if not _ok:
    try:
        _ok = ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
    except Exception:  # noqa: BLE001
        _ok = False
print(f"抓图进程 DPI 感知: {bool(_ok)}")

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VIEWS = ["app", "model", "speed", "quota"]
BASE_RGB = (0x0C, 0x12, 0x20)      # 面板底色，用作「确实抓到面板了」的判据


def find_panel():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "TokenBoardWindow":
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out[0] if out else None


def raise_to_front(hwnd) -> None:
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)


def looks_like_panel(path: str) -> bool:
    from PIL import Image
    with Image.open(path) as img:
        px = img.convert("RGB").getpixel((6, 6))
    return all(abs(px[i] - BASE_RGB[i]) < 18 for i in range(3))


def main() -> int:
    hwnd = find_panel()
    if not hwnd:
        print("没找到主面板窗口")
        return 1
    print(f"面板 hwnd={hwnd}")

    ok_all = True
    for i, name in enumerate(VIEWS):
        user32.SendMessageW(hwnd, WM_KEYDOWN, ord("1") + i, 0)
        user32.SendMessageW(hwnd, WM_KEYUP, ord("1") + i, 0)
        time.sleep(1.4)          # 额度视图要等网络请求
        out = os.path.join(ROOT, "tools", f"view_{name}.png")
        r = wintypes.RECT()
        for attempt in range(4):
            raise_to_front(hwnd)
            time.sleep(0.5)
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            size = screen_capture.grab(r.left, r.top, r.right - r.left,
                                       r.bottom - r.top, out)
            if looks_like_panel(out):
                break
            print(f"    ({name}) 第 {attempt + 1} 次抓到的是别的窗口，重试")
            time.sleep(0.6)
        else:
            ok_all = False
        print(f"  {name} -> {out} {size[0]}x{size[1]}"
              f"{'' if looks_like_panel(out) else '  ⚠ 没抓到面板'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
