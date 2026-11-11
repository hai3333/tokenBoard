#!/usr/bin/env python3
"""验证单实例：第二次启动应唤起已运行实例的面板，而不是开第二个窗口。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = r"D:\个人资料\项目\token看板"
user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass


def count_windows(pid: int | None = None) -> list:
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if "TokenBoardWindow" not in cls.value:
            return True
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        r = wintypes.RECT()
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
        out.append((hwnd, wpid.value, buf.value, r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumWindows(cb, 0)
    return out


def main() -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    print("=== 第一次启动 ===")
    p1 = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    time.sleep(10)
    wins = count_windows(p1.pid)
    print(f"pid={p1.pid} 窗口数={len(wins)}")
    for w in wins:
        print("   ", w)

    print("\n=== 第二次启动（应唤起已有实例，不开新窗口） ===")
    p2 = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    rc = p2.wait(timeout=30)
    print(f"第二个进程退出码 = {rc}")
    time.sleep(2)
    wins2 = count_windows()
    tk = [w for w in wins2 if w[2] == "TokenBoard"]
    print(f"系统内 TokenBoard 窗口数 = {len(tk)}")
    for w in tk:
        print("   ", w)
    print(f"第一个进程仍存活 = {p1.poll() is None}")

    p1.terminate()
    try:
        p1.wait(timeout=5)
    except Exception:  # noqa: BLE001
        p1.kill()
    print("\n=== 退出后端口应释放 ===")
    time.sleep(1)
    p3 = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    time.sleep(8)
    wins3 = count_windows(p3.pid)
    print(f"重新启动后 pid={p3.pid} 窗口数={len(wins3)} 存活={p3.poll() is None}")
    p3.terminate()
    try:
        p3.wait(timeout=5)
    except Exception:  # noqa: BLE001
        p3.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
