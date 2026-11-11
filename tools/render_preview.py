#!/usr/bin/env python3
"""把面板三个视图渲染成 PNG，方便快速看设计效果。

注意：渲染进程退出时 GDI 收尾会把已经写好的 PNG 文件内容弄坏
（长度 +1024、内容被内存页覆盖），所以这里让**子进程渲染**，
PNG 字节走管道回传给父进程，由父进程落盘 —— 管道里的数据不受影响。
"""
import ctypes
import io
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from PIL import Image

OUT = r"D:\个人资料\项目\token看板\tools"
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def capture(hwnd) -> Image.Image:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)
    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return img


def child(view: str):
    """子进程：建面板、渲染、把 PNG 字节写到 stdout。"""
    from tokenboard.config import DB_PATH, ensure_dirs
    from tokenboard.scanner import Scanner
    from tokenboard.store import Store
    from tokenboard.ui.panel import Panel

    ensure_dirs()
    store = Store(DB_PATH)
    panel = Panel(store, Scanner(store))
    panel.create()
    panel.show()
    time.sleep(0.4)

    if view == "app":
        panel._view_idx = 0
        panel._period_idx = 3
    elif view == "model":
        panel._view_idx = 1
    else:
        from tokenboard.quota import fetch_all
        panel._view_idx = 2
        panel._quota = fetch_all()

    panel.invalidate()
    time.sleep(0.8)
    img = capture(panel.hwnd)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    sys.stdout.buffer.write(bio.getvalue())
    sys.stdout.buffer.flush()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2])
        return 0

    for view, name in (("app", "design_app.png"),
                       ("model", "design_model.png"),
                       ("quota", "design_quota.png")):
        p = subprocess.run([sys.executable, os.path.abspath(__file__),
                            "--child", view], capture_output=True)
        if p.returncode != 0:
            print(f"  {name} 子进程失败:", p.stderr.decode("utf-8", "replace")[-400:])
            continue
        data = p.stdout
        path = os.path.join(OUT, name)
        with open(path, "wb") as f:
            f.write(data)
        head = " ".join(f"{b:02X}" for b in data[:8])
        ok = data[:4] == b"\x89PNG"
        print(f"  {name:<18} {len(data):>7} 头={'OK' if ok else 'BAD'}  {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
