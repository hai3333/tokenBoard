#!/usr/bin/env python3
"""验证免安装单文件 exe：换个目录跑能不能正常工作。"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = Path(r"D:\个人资料\项目\token看板\dist\portable\TokenBoard.exe")
TEST_DIR = Path(os.environ["USERPROFILE"]) / "Desktop" / "_tb_portable_test"
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass


class NID(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", ctypes.c_byte * 16)]


class RECT(ctypes.Structure):
    _fields_ = [("l", wintypes.LONG), ("t", wintypes.LONG),
                ("r", wintypes.LONG), ("b", wintypes.LONG)]


def find_win(pid):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == "TokenBoardWindow":
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            # PyInstaller onefile 会再拉一个子进程跑真正的应用，
            # 所以窗口不一定在启动进程自己的 PID 上
            out.append((h, p.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


def main() -> int:
    # 先停掉已安装的那个，避免单实例把它顶掉
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    time.sleep(2)

    TEST_DIR.mkdir(parents=True, exist_ok=True)
    dst = TEST_DIR / "TokenBoard.exe"
    shutil.copy2(SRC, dst)
    print(f"复制到: {dst}")

    t0 = time.time()
    proc = subprocess.Popen([str(dst)], cwd=str(TEST_DIR))
    print("等待启动 ...")
    win = None
    for _ in range(40):
        time.sleep(0.5)
        if proc.poll() is not None:
            print(f"!! 退出，退出码 {proc.returncode}")
            return 1
        win = find_win(proc.pid)
        if win:
            break
    if not win:
        print("!! 没出现窗口")
        proc.terminate()
        return 1
    print(f"  启动耗时 {time.time() - t0:.1f}s（onefile 要先解压到 temp）")

    r = wintypes.RECT()
    user32.GetWindowRect(win[0][0], ctypes.byref(r))
    print(f"  窗口: ({r.left},{r.top})-({r.right},{r.bottom})  "
          f"{r.right - r.left}x{r.bottom - r.top}")
    print(f"  窗口所属进程 pid={win[0][1]}（启动进程 {proc.pid}）")

    nid = NID()
    nid.cbSize = ctypes.sizeof(NID)
    nid.hWnd = win[0][0]
    nid.uID = 0
    rr = RECT()
    print(f"  托盘图标: {'已注册' if shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(rr)) else '未注册'}")

    time.sleep(9)
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    img.crop((r.left, r.top, r.right, r.bottom)).save(
        r"D:\个人资料\项目\token看板\tools\portable_shot.png")

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        proc.kill()

    shutil.rmtree(TEST_DIR, ignore_errors=True)
    print("\n日志尾部:")
    log = Path(os.environ["LOCALAPPDATA"]) / "TokenBoard" / "tokenboard.log"
    if log.exists():
        with open(log, encoding="utf-8", errors="replace") as f:
            print(f.read()[-500:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
