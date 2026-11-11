#!/usr/bin/env python3
"""1) 完整 transport.js（看请求怎么签名/带什么参数）；2) cc-switch.exe 里的火山 usage 模板。"""
import os
import re
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from tools.asar_read import read_asar, find_files  # noqa: E402

ASAR = r"D:\software\minimaxcode\MiniMax Code\resources\app.asar"
header, data, base = read_asar(ASAR)

for p, info in find_files(header):
    if p.endswith("adapters/quota/transport.js"):
        off, size = int(info["offset"]), int(info["size"])
        print("=" * 78)
        print("### transport.js 全文")
        print("=" * 78)
        print(data[base + off: base + off + size].decode("utf-8", "replace"))
        break

print("\n" + "=" * 78)
print("### cc-switch.exe 里的火山 usage 模板")
print("=" * 78)
exe = r"D:\software\CC-Switch-v3.9.0-3-Windows-Portable\css15\cc-switch.exe"
if os.path.exists(exe):
    blob = open(exe, "rb").read()
    for pat in (rb"volcengine", rb"ark\.cn-beijing", rb"coding_plan", rb"usage_script"):
        for m in re.finditer(pat, blob, re.I):
            s = max(0, m.start() - 700)
            frag = blob[s:m.start() + 900]
            txt = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b" ", frag).decode("utf-8", "replace")
            print(f"\n--- 命中 {pat.decode()} @ {m.start()} ---")
            print(txt)
            break
else:
    print("  cc-switch.exe 不存在")
