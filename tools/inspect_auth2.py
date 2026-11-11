#!/usr/bin/env python3
"""看 auth.json 的记录结构（脱敏）+ routingHeaders 是什么。"""
import json
import os
import re
import sys

sys.path.insert(0, r"D:\个人资料\项目\token_board") if False else None
sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from tools.asar_read import read_asar, find_files  # noqa: E402

HOME = os.path.expanduser("~")
p = os.path.join(HOME, ".minimax", "auth", "prod", "cn", "mcode-public", "auth.json")
data = json.load(open(p, encoding="utf-8"))
print("=" * 78)
print("auth.json 顶层键:", list(data.keys()))
recs = data.get("records") or {}
print(f"records 条数: {len(recs)}")
for k, v in recs.items():
    print(f"\n  key = {k!r}")
    for kk, vv in v.items():
        if isinstance(vv, str) and len(vv) > 30:
            print(f"     {kk}: <str len={len(vv)}> {vv[:12]}...")
        else:
            print(f"     {kk}: {vv!r}"[:220])

print("\n" + "=" * 78)
print("找 routingHeaders 定义")
print("=" * 78)
ASAR = r"D:\software\minimaxcode\MiniMax Code\resources\app.asar"
header, blob, base = read_asar(ASAR)
for path, info in find_files(header):
    if not path.endswith(".js"):
        continue
    off, size = int(info.get("offset", 0)), int(info.get("size", 0))
    if size == 0 or size > 2_000_000:
        continue
    txt = blob[base + off: base + off + size].decode("utf-8", "replace")
    if "routingHeaders" in txt and "X-Group-Id" in txt:
        i = txt.find("routingHeaders")
        print(f"### {path}")
        print(re.sub(r"\s+", " ", txt[max(0, i - 1200):i + 700])[:2600])
        break

print("\n" + "=" * 78)
print("找 groupId 来源（plan.groupId）")
print("=" * 78)
for path, info in find_files(header):
    if not path.endswith(".js"):
        continue
    off, size = int(info.get("offset", 0)), int(info.get("size", 0))
    if size == 0 or size > 2_000_000:
        continue
    txt = blob[base + off: base + off + size].decode("utf-8", "replace")
    if "groupId" in txt and "coding_plan" in txt:
        i = txt.find("groupId")
        print(f"### {path}")
        print(re.sub(r"\s+", " ", txt[max(0, i - 1500):i + 500])[:2600])
        break
