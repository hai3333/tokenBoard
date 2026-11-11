"""截图：起一个临时实例，用 DWM 抓客户区（不抢前台、不依赖屏幕遮挡）。

用法：
    python tools/shot.py out.png [额外参数...]
环境变量照旧生效（TOKENBOARD_VIEW / TOKENBOARD_PERIOD / TOKENBOARD_EXPAND），
另有 SHOT_SIZE=宽x高 可以先改窗口尺寸再截。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wincap  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
user32 = ctypes.windll.user32

# 本进程也要 DPI 感知：否则 GetClientRect 返回的是缩放后的虚拟尺寸，
# PrintWindow 只会画左上角一块，右边被裁掉。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass


def find_window(pid: int):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        if not user32.IsWindowVisible(h):
            return True
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value != pid:
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value == "TokenBoardWindow":
            found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "tools", "ui_shot_new.png")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-m", "tokenboard.app"],
                            cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        hwnd = None
        for _ in range(40):
            time.sleep(0.4)
            hwnd = find_window(proc.pid)
            if hwnd:
                break
        if not hwnd:
            print("!! 没找到窗口")
            return 1
        time.sleep(float(os.environ.get("SHOT_WAIT", "2.5")))   # 等首帧 + 首次扫描

        size = os.environ.get("SHOT_SIZE", "").strip()
        if size and "x" in size:
            w, h = (int(v) for v in size.lower().split("x"))
            scale = wincap and 1.0
            try:
                from tokenboard.ui.win32 import enable_dpi_awareness
                scale = enable_dpi_awareness()
            except Exception:  # noqa: BLE001
                pass
            user32.SetWindowPos(hwnd, 0, 0, 0, int(w * scale), int(h * scale),
                                0x0004 | 0x0010)     # SWP_NOZORDER|SWP_NOACTIVATE
            time.sleep(1.2)

        img = None
        # DWM 的重定向表面有时还没更新，第一张截出来是全黑 —— 重试到有画面为止
        for attempt in range(8):
            user32.InvalidateRect(hwnd, None, True)
            user32.UpdateWindow(hwnd)
            time.sleep(0.45)
            img = wincap.capture_client(hwnd)
            if img.getextrema() != ((0, 0), (0, 0), (0, 0)):
                break
            print(f"  第 {attempt + 1} 次截图全黑，重试")
        img.save(out)
        print("saved", out, img.size)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())