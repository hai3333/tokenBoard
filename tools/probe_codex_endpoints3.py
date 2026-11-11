#!/usr/bin/env python3
"""打印包含关键片段的完整可打印字符串，定位额度 HTTP 端点。"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXE = os.path.expanduser("~/.codex/plugins/.plugin-appserver/codex.exe")
NEEDLES = ("backend-api", "rateLimits/read", "rate_limits", "accounts/",
           "chatgpt.com", "wham")

str_re = re.compile(rb"[\x20-\x7e]{8,500}")
found = {n: set() for n in NEEDLES}

chunk = 8 * 1024 * 1024
tail = b""
with open(EXE, "rb") as f:
    while True:
        buf = f.read(chunk)
        if not buf:
            break
        buf = tail + buf
        for m in str_re.finditer(buf):
            s = m.group().decode("ascii", "replace")
            for n in NEEDLES:
                if n in s:
                    found[n].add(s[:300])
        tail = buf[-700:]

for n in NEEDLES:
    items = sorted(found[n])
    # 过滤掉 cargo 路径噪音
    items = [s for s in items
             if ".cargo\\" not in s and "registry/src" not in s]
    print(f"\n=== 含 {n!r} 的字符串（{len(items)} 条）===")
    for s in items[:40]:
        print("  ", s)
