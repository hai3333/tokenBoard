#!/usr/bin/env python3
"""从 codex.exe 二进制里扫出额度/用量相关的 URL 与 JSON 字段名。"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXE = os.path.expanduser("~/.codex/plugins/.plugin-appserver/codex.exe")
if not os.path.isfile(EXE):
    EXE = r"D:\software\minimaxcode\MiniMax Code\resources\codex.exe"

KEYS = (
    "backend-api", "wham", "usage", "rate_limit", "rate-limit",
    "rateLimits", "primary_window", "secondary_window", "credits",
    "resets_at", "resetsIn", "plan_type", "subscription",
)

print(f"扫描: {EXE}")
if not os.path.isfile(EXE):
    print("找不到 codex.exe")
    sys.exit(1)

print(f"大小: {os.path.getsize(EXE) / 1048576:.0f} MB")

# 只保留 ASCII 可见字符串
chunk_size = 8 * 1024 * 1024
overlap = 512
str_re = re.compile(rb"[\x20-\x7e]{6,600}")

urls = set()
fields = set()
tail = b""

with open(EXE, "rb") as f:
    while True:
        buf = f.read(chunk_size)
        if not buf:
            break
        buf = tail + buf
        for m in str_re.finditer(buf):
            s = m.group().decode("ascii", "replace")
            sl = s.lower()
            if "http" in sl and ("usage" in sl or "wham" in sl or
                                 "rate" in sl or "credit" in sl):
                urls.add(s[:300])
            if "chatgpt.com" in sl and "/" in sl:
                urls.add(s[:300])
            if re.search(r"rate_?limit", sl):
                fields.add(s[:200])
        tail = buf[-overlap:]

print("\n=== 含 usage/rate/wham 的 URL ===")
for u in sorted(urls):
    if len(u) < 300:
        print("  ", u)

print("\n=== rate_limit 相关字符串（最多 60 条）===")
for s in sorted(fields)[:60]:
    print("  ", s)
