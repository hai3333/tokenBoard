#!/usr/bin/env python3
"""定位 design_app.png 头部损坏的原因。"""
import ctypes
import os
import sys
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from PIL import Image

OUT = r"D:\个人资料\项目\token看板\tools"
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

W, H = 400, 200


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def hexdump(p, n=16):
    with open(p, "rb") as f:
        d = f.read(n)
    return " ".join(f"{b:02X}" for b in d)


# 1) 纯 PIL 写文件
p1 = os.path.join(OUT, "_t_pil.png")
Image.new("RGB", (W, H), (10, 20, 30)).save(p1)
print("1 PIL 直写        :", hexdump(p1))

# 2) frombuffer + save（和 capture 一样）
hdc = user32.GetDC(None)
mem = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, W, H)
gdi32.SelectObject(mem, bmp)
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
p2 = os.path.join(OUT, "_t_frombuf.png")
img.save(p2)
print("2 frombuffer+save :", hexdump(p2))
gdi32.DeleteObject(bmp)
gdi32.DeleteDC(mem)
user32.ReleaseDC(None, hdc)

# 3) 先存临时文件再 shutil 过去
import shutil
tmp = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "_t_tmp.png")
img.save(tmp)
p3 = os.path.join(OUT, "_t_copy.png")
shutil.copy2(tmp, p3)
print("3 临时+复制       :", hexdump(p3))
