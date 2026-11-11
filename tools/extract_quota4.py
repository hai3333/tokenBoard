#!/usr/bin/env python3
"""1) 确认 MiniMax 百分比口径（U/H 定义 + 渲染处）；2) 挖 cc-switch 里的火山 usage 模板。"""
import os
import re
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from tools.asar_read import read_asar, find_files  # noqa: E402

ASAR = r"D:\software\minimaxcode\MiniMax Code\resources\app.asar"
header, blob, base = read_asar(ASAR)

print("=" * 78)
print("### U / H 的定义 + window_5h 渲染处")
print("=" * 78)
for path, info in find_files(header):
    if not path.endswith(".js"):
        continue
    off, size = int(info.get("offset", 0)), int(info.get("size", 0))
    if size == 0 or size > 2_000_000:
        continue
    txt = blob[base + off: base + off + size].decode("utf-8", "replace")
    if "current_interval_remaining_percent" not in txt:
        continue
    flat = re.sub(r"\s+", " ", txt)
    # U / H 定义
    for name in ("function U(", "function H(", "U=(", "H=("):
        i = flat.find(name)
        if i > 0:
            print(f"\n[{name}] ...{flat[max(0, i - 260):i + 320]}...")
    # 渲染 window_5h
    for m in re.finditer(r"window_5h", flat):
        i = m.start()
        print(f"\n[window_5h 用法] ...{flat[max(0, i - 900):i + 400]}...")
        break
    break

print("\n" + "=" * 78)
print("### cc-switch.exe 里的火山/订阅 usage 模板")
print("=" * 78)
exe = r"D:\software\CC-Switch-v3.9.0-3-Windows-Portable\css15\cc-switch.exe"
if os.path.exists(exe):
    b = open(exe, "rb").read()
    print(f"  文件大小 {len(b) / 1048576:.1f} MB")
    for pat in (rb"coding_plan", rb"volcengine", rb"ark\.cn-beijing", rb"quota"):
        found = 0
        for m in re.finditer(pat, b, re.I):
            s = max(0, m.start() - 500)
            frag = b[s:m.start() + 800]
            txt = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b" ", frag).decode("utf-8", "replace")
            if not re.search(r"[\x20-\x7e一-鿿]{40,}", txt):
                continue
            print(f"\n--- {pat.decode()} @ {m.start()} ---")
            print(txt)
            found += 1
            if found >= 2:
                break
        if not found:
            print(f"  {pat.decode()}: 无有效文本命中")
else:
    print("  不存在")
