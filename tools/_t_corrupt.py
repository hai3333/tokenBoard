#!/usr/bin/env python3
"""谁把 PNG 弄坏的？写完立刻校验 -> 睡一会再校验 -> 退出后再校验。"""
import ctypes
import hashlib
import os
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from PIL import Image

OUT = r"D:\个人资料\项目\token看板\tools"
P = os.path.join(OUT, "_probe.png")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
W, H = 300, 150


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()[:12]


def head(p):
    return " ".join(f"{b:02X}" for b in open(p, "rb").read(8))


hdc = user32.GetDC(None)
mem = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, W, H)
gdi32.SelectObject(mem, bmp)


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


bi = BIH()
bi.biSize = ctypes.sizeof(BIH)
bi.biWidth = W
bi.biHeight = -H
bi.biPlanes = 1
bi.biBitCount = 32
bi.biCompression = 0
buf = ctypes.create_string_buffer(W * H * 4)
gdi32.GetDIBits(mem, bmp, 0, H, buf, ctypes.byref(bi), 0)

img = Image.frombuffer("RGBA", (W, H), buf, "raw", "BGRA", 0, 1).convert("RGB")
img.save(P)
print("写完立刻   :", md5(P), head(P))

time.sleep(3)
print("睡 3 秒后  :", md5(P), head(P))

# 再用 frombytes 走一遍（强制拷贝）
img2 = Image.frombytes("RGB", (W, H), img.tobytes())
img2.save(P)
print("重写后     :", md5(P), head(P))

time.sleep(3)
print("再睡 3 秒  :", md5(P), head(P))

try:
    Image.open(P).load()
    print("PIL 能打开 : 是")
except Exception as e:
    print("PIL 能打开 : 否", e)

gdi32.DeleteObject(bmp)
gdi32.DeleteDC(mem)
user32.ReleaseDC(None, hdc)
print("进程即将退出")
