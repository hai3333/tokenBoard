#!/usr/bin/env python3
"""干净启动，打印所有 TokenBoard 窗口的详细信息。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"D:\个人资料\项目\token看板"
user32 = ctypes.windll.user32


def dump(tag):
    print(f"  --- {tag} ---")

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow":
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            r = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            print(f"     hwnd={h} pid={pid.value} rect=({r.left},{r.top})-"
                  f"({r.right},{r.bottom}) size={r.right - r.left}x{r.bottom - r.top} "
                  f"visible={user32.IsWindowVisible(h)} "
                  f"iconic={user32.IsIconic(h)}")
        return True

    user32.EnumWindows(cb, 0)


def main():
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(3)
    dump("启动前")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "TOKENBOARD_VIEW": "model", "TOKENBOARD_PERIOD": "all"}
    p = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT, env=env)
    for t in (3, 6, 10, 14):
        time.sleep(t - (3 if t == 3 else 0) if t == 3 else (t - (3 if t == 3 else 0)))
        dump(f"t+{t}s")
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:  # noqa: BLE001
        p.kill()
    return 0


if __name__ == "__main__":
    main()
