#!/usr/bin/env python3
"""Final shapes: Gemini CLI chats + Antigravity transcripts (os.walk for dotdirs)."""
import sys
import os
import json
import re

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

print("=" * 72)
print("GEMINI CLI chats")
print("=" * 72)
base = os.path.join(HOME, ".gemini/tmp")
for root, dirs, files in os.walk(base):
    for f in files:
        if not f.endswith(".json"):
            continue
        p = os.path.join(root, f)
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except Exception:  # noqa: BLE001
            continue
        print(f"\n-- {os.path.relpath(p, base)} ({len(txt)} B)")
        print("   ", txt[:900].replace("\n", " "))

print("\n" + "=" * 72)
print("ANTIGRAVITY brain transcripts (os.walk)")
print("=" * 72)
ag = os.path.join(HOME, ".gemini/antigravity/brain")
found = 0
scanned = 0
for root, dirs, files in os.walk(ag):
    for f in files:
        if "transcript" not in f or not f.endswith(".jsonl"):
            continue
        p = os.path.join(root, f)
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except Exception:  # noqa: BLE001
            continue
        scanned += 1
        m = re.search(r"(input[_ ]?tokens|output[_ ]?tokens|total[_ ]?tokens|promptTokenCount|candidatesTokenCount)", txt, re.I)
        if m:
            found += 1
            if found <= 2:
                print(f"\n  HIT {os.path.relpath(p, ag)}")
                for mm in list(re.finditer(r"(input[_ ]?tokens|output[_ ]?tokens|total[_ ]?tokens|promptTokenCount|candidatesTokenCount|cachedContentTokenCount)", txt, re.I))[:5]:
                    s = max(0, mm.start() - 300)
                    print("     ", txt[s:mm.start() + 320].replace("\n", " ")[:600])
print(f"\n  scanned={scanned} with-token-fields={found}")
