#!/usr/bin/env python3
"""Inspect Codex rollout payload shapes to avoid double-counting cumulative usage."""
import sys
import os
import json
import glob
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

files = sorted(glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True),
               key=os.path.getmtime, reverse=True)
print(f"{len(files)} codex rollout files")

shapes = Counter()
samples = {}
for p in files[:6]:
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            ptype = o.get("type")
            payload = o.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            ptype2 = payload.get("type")
            key = (ptype, ptype2)
            shapes[key] += 1
            if "token" in json.dumps(payload).lower() and key not in samples:
                samples[key] = (os.path.basename(p), o)

print("\n--- (outer type, payload.type) histogram ---")
for k, v in shapes.most_common(20):
    print(f"  {str(k):<45} {v}")

print("\n--- samples containing token ---")
for key, (name, o) in samples.items():
    print(f"\n### {key}  ({name})")
    s = json.dumps(o, ensure_ascii=False)
    print("   ", s[:1500])
