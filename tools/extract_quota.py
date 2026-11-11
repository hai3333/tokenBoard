#!/usr/bin/env python3
"""抠出 MiniMax 额度相关 chunk，并找本地 accessToken。"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.asar_read import read_asar, find_files  # noqa: E402

ASAR = r"D:\software\minimaxcode\MiniMax Code\resources\app.asar"
header, data, base = read_asar(ASAR)
files = find_files(header)

# 1) 哪些 chunk 里出现了 coding_plan / remains / 5小时限额相关
KEYS = (b"coding_plan", b"remains", b"usage_5h", b"five_hour", b"5h_limit",
        b"weekly_limit", b"OPEN_PLATFORM_ORIGINS")
hits = []
for p, info in files:
    off = int(info.get("offset", 0))
    size = int(info.get("size", 0))
    if size > 3_000_000 or size == 0:
        continue
    blob = data[base + off: base + off + size]
    if any(k in blob for k in KEYS):
        hits.append((p, size, blob))

print(f"命中 {len(hits)} 个 chunk")
for p, size, _ in hits[:25]:
    print(f"   {p} ({size})")

# 2) 把最相关的几个抠出来看
for p, size, blob in hits:
    if "subscription-quota" in p or p.endswith(".js") and b"coding_plan" in blob:
        txt = blob.decode("utf-8", "replace")
        print("\n" + "=" * 78)
        print(f"### {p} ({size})")
        print("=" * 78)
        for kw in ("coding_plan", "remains", "5h", "weekly", "quota",
                   "reset", "used", "total", "limit"):
            for m in re.finditer(re.escape(kw), txt):
                s = max(0, m.start() - 200)
                frag = re.sub(r"\s+", " ", txt[s:m.start() + 260])
                print(f"  [{kw}] ...{frag}...")
                break

# 3) OPEN_PLATFORM_ORIGINS 定义
for p, size, blob in hits:
    txt = blob.decode("utf-8", "replace")
    m = re.search(r"OPEN_PLATFORM_ORIGINS\s*=\s*\{.{0,600}", txt, re.S)
    if m:
        print("\n=== OPEN_PLATFORM_ORIGINS ===")
        print(m.group()[:700])
        break
else:
    for p, info in files:
        off = int(info.get("offset", 0))
        size = int(info.get("size", 0))
        if size == 0 or size > 3_000_000:
            continue
        blob = data[base + off: base + off + size]
        m = re.search(rb"OPEN_PLATFORM_ORIGINS\s*=\s*\{.{0,600}", blob, re.S)
        if m:
            print("\n=== OPEN_PLATFORM_ORIGINS (其它文件) ===")
            print(m.group().decode("utf-8", "replace")[:700])
            break

print("\n" + "=" * 78)
print("=== ~/.minimax/auth 目录 ===")
print("=" * 78)
for root, dirs, fnames in os.walk(os.path.expanduser(r"~\.minimax\auth")):
    for f in fnames:
        p = os.path.join(root, f)
        print(f"  {p}  ({os.path.getsize(p)})")
