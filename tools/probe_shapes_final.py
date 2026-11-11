#!/usr/bin/env python3
"""Exact usage payload shapes: opencode message.data, antigravity transcripts."""
import sys
import os
import json
import glob
import sqlite3
import re
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

print("=" * 72)
print("OPENCODE : assistant message.data tokens shape")
print("=" * 72)
db = os.path.join(HOME, ".local/share/opencode/opencode.db")
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
shapes = Counter()
samples = []
for r in conn.execute("select id, session_id, time_created, data from message"):
    try:
        d = json.loads(r["data"])
    except Exception:  # noqa: BLE001
        continue
    if d.get("role") != "assistant":
        continue
    tk = d.get("tokens")
    if tk is None:
        continue
    shapes[tuple(sorted(tk.keys()))] += 1
    if len(samples) < 3:
        samples.append((r["id"], r["session_id"], r["time_created"], d))
print("  token shapes:", dict(shapes.most_common(8)))
for sid, ssid, tc, d in samples:
    print(f"\n  id={sid} session={ssid} ts={tc}")
    print("   ", json.dumps({k: v for k, v in d.items() if k != "parts"}, ensure_ascii=False)[:700])

print("\n  -- assistant message count / total token agg --")
tot = {"input": 0, "output": 0, "reasoning": 0, "read": 0, "write": 0}
n = 0
for r in conn.execute("select data from message"):
    try:
        d = json.loads(r["data"])
    except Exception:  # noqa: BLE001
        continue
    tk = d.get("tokens")
    if not isinstance(tk, dict):
        continue
    n += 1
    tot["input"] += tk.get("input", 0) or 0
    tot["output"] += tk.get("output", 0) or 0
    tot["reasoning"] += tk.get("reasoning", 0) or 0
    cache = tk.get("cache") or {}
    tot["read"] += cache.get("read", 0) or 0
    tot["write"] += cache.get("write", 0) or 0
print(f"   messages with tokens: {n}  agg={tot}")

print("\n" + "=" * 72)
print("ANTIGRAVITY transcripts")
print("=" * 72)
ag = os.path.join(HOME, ".gemini/antigravity/brain")
hits = 0
scanned = 0
for p in sorted(glob.glob(os.path.join(ag, "**", "transcript*.jsonl"), recursive=True),
                key=os.path.getmtime, reverse=True)[:60]:
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception:  # noqa: BLE001
        continue
    scanned += 1
    if re.search(r"(input[_ ]?tokens|output[_ ]?tokens|total[_ ]?tokens|promptTokenCount|candidatesTokenCount)", txt, re.I):
        hits += 1
        if hits <= 2:
            print(f"\n  HIT {os.path.relpath(p, ag)}")
            for m in list(re.finditer(r"(input[_ ]?tokens|output[_ ]?tokens|total[_ ]?tokens|promptTokenCount|candidatesTokenCount|cachedContentTokenCount|usageMetadata)", txt, re.I))[:5]:
                s = max(0, m.start() - 260)
                print("     ", txt[s:m.start() + 300].replace("\n", " ")[:540])
print(f"\n  scanned={scanned} with-token-fields={hits}")

print("\n" + "=" * 72)
print("GEMINI CLI : any chat/usage logs?")
print("=" * 72)
for pat in ("tmp/**/logs.json", "tmp/**/*.json", "sessions/**/*.jsonl"):
    fs = glob.glob(os.path.join(HOME, ".gemini", pat), recursive=True)
    print(f"  {pat}: {len(fs)}")
    for f in fs[:3]:
        print("     ", f, os.path.getsize(f))
