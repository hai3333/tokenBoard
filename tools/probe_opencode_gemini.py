#!/usr/bin/env python3
"""Probe opencode + gemini token storage (part 2)."""
import sys
import os
import json
import glob
import re
import sqlite3
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

print("=" * 72)
print("OPENCODE candidate dirs")
print("=" * 72)
for cand in (os.path.join(HOME, ".local/share/opencode"), os.path.join(HOME, ".config/opencode"),
             os.path.join(HOME, ".opencode"), os.path.join(HOME, ".local/state/opencode"),
             os.path.join(HOME, ".cache/opencode")):
    print(f"\n--- {cand}  exists={os.path.isdir(cand)}")
    if os.path.isdir(cand):
        for e in sorted(os.listdir(cand))[:20]:
            full = os.path.join(cand, e)
            print(f"     {'[D]' if os.path.isdir(full) else '[F]'} {e}"
                  + ("" if os.path.isdir(full) else f" ({os.path.getsize(full)})"))

print("\n" + "=" * 72)
print("OPENCODE: global search for storage dir")
print("=" * 72)
for base in (os.path.join(HOME, ".local/share"), os.path.join(HOME, ".config"), HOME):
    if not os.path.isdir(base):
        continue
    for e in os.listdir(base):
        if "opencode" in e.lower():
            p = os.path.join(base, e)
            print(f"   HIT {p}")
            for root, dirs, files in os.walk(p):
                dirs[:] = dirs[:6]
                for f in files[:10]:
                    fp = os.path.join(root, f)
                    try:
                        print(f"      {os.path.relpath(fp, p)}  ({os.path.getsize(fp)})")
                    except Exception:  # noqa: BLE001
                        pass
                break

print("\n" + "=" * 72)
print("GEMINI CLI : ~/.gemini")
print("=" * 72)
g = os.path.join(HOME, ".gemini")
if os.path.isdir(g):
    for root, dirs, files in os.walk(g):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for f in files:
            p = os.path.join(root, f)
            try:
                sz = os.path.getsize(p)
            except Exception:  # noqa: BLE001
                continue
            rel = os.path.relpath(p, g)
            print(f"   {rel}  ({sz})")
            if sz < 4 * 1024 * 1024 and f.endswith((".json", ".jsonl")):
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        txt = fh.read()
                except Exception:  # noqa: BLE001
                    continue
                m = re.search(r"(input_tokens|output_tokens|total_tokens|promptTokenCount|candidatesTokenCount)", txt)
                if m:
                    print("        >>> HAS TOKEN FIELDS")
                    for mm in list(re.finditer(r"(input_tokens|output_tokens|total_tokens|promptTokenCount|candidatesTokenCount|cachedContentTokenCount)", txt))[:4]:
                        s = max(0, mm.start() - 180)
                        print("        ", txt[s:mm.start() + 240].replace("\n", " ")[:420])
else:
    print("  ~/.gemini NOT FOUND")

print("\n" + "=" * 72)
print("CODEX: sample token_count event shape")
print("=" * 72)
files = sorted(glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True),
               key=os.path.getmtime, reverse=True)
for p in files[:1]:
    print(f"  -- {p}")
    with open(p, encoding="utf-8", errors="replace") as f:
        for i, ln in enumerate(f):
            if i > 300:
                break
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            s = json.dumps(o, ensure_ascii=False)
            if "token" in s.lower():
                print(f"   type={o.get('type')} :: {s[:700]}")
                if i > 40:
                    break
