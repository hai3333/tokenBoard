#!/usr/bin/env python3
"""从正在使用的配置里找真实的火山 key（只打印前缀+长度）。"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

CANDIDATES = [
    ("~/.claude/settings.json", "claude settings"),
    ("~/.claude/settings.local.json", "claude settings.local"),
    ("~/.codex/config.toml", "codex config"),
    ("~/.codex/auth.json", "codex auth"),
    ("~/.minimax/config.yaml", "minimax config"),
    ("~/.zcode/v2/provider_config.json", "zcode provider"),
    ("~/.zcode/v2/credentials.json", "zcode credentials"),
]

for rel, label in CANDIDATES:
    p = os.path.join(HOME, rel[2:])
    if not os.path.exists(p):
        continue
    raw = open(p, encoding="utf-8", errors="replace").read()
    hits = set()
    for m in re.finditer(r"(ark-[A-Za-z0-9\-_]{10,60})", raw):
        hits.add(m.group(1))
    for m in re.finditer(r"(sk-[A-Za-z0-9\-_]{10,60})", raw):
        hits.add(m.group(1))
    for m in re.finditer(r"(mmoat_[A-Za-z0-9\-_]{10,60})", raw):
        hits.add(m.group(1))
    base = set(re.findall(r"https?://[A-Za-z0-9.\-]+", raw))
    print(f"\n--- {label}: {p} ---")
    for h in sorted(hits):
        print(f"    key {h[:14]}...  (len={len(h)})")
    for b in sorted(base):
        if "volces" in b or "minimax" in b or "bailian" in b:
            print(f"    base {b}")
    if not hits and not base:
        print("    (没找到 key/base)")
