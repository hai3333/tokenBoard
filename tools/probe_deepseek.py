#!/usr/bin/env python3
"""Hunt DeepSeek dsh-desktop token/usage storage."""
import sys
import os
import json
import glob
import re
import sqlite3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = os.path.expanduser("~")
DS = os.path.join(HOME, "AppData/Roaming/@deepseek-ai/dsh-desktop")

SKIP = {"Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache",
        "GrShaderCache", "ShaderCache", "GPUPersistentCache", "blob_storage",
        "Network", "DIPS", "Crashpad"}

print("=" * 70)
print("dsh-desktop file inventory (caches skipped)")
print("=" * 70)
for root, dirs, files in os.walk(DS):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for f in files:
        p = os.path.join(root, f)
        rel = os.path.relpath(p, DS)
        try:
            sz = os.path.getsize(p)
        except Exception:  # noqa: BLE001
            sz = -1
        print(f"  {rel}  ({sz})")

print("\n" + "=" * 70)
print("Search small text-ish files for token/usage keywords")
print("=" * 70)
KEY = re.compile(rb"(input_?tokens|output_?tokens|prompt_?tokens|completion_?tokens|total_?tokens|usage)", re.I)
for root, dirs, files in os.walk(DS):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for f in files:
        p = os.path.join(root, f)
        try:
            sz = os.path.getsize(p)
        except Exception:  # noqa: BLE001
            continue
        if sz > 40 * 1024 * 1024 or sz == 0:
            continue
        try:
            with open(p, "rb") as fh:
                blob = fh.read()
        except Exception:  # noqa: BLE001
            continue
        if KEY.search(blob):
            # count hits
            hits = len(KEY.findall(blob))
            print(f"\n  HIT {os.path.relpath(p, DS)}  size={sz} matches={hits}")
            for m in list(KEY.finditer(blob))[:4]:
                s = max(0, m.start() - 220)
                frag = blob[s:m.start() + 320]
                txt = frag.decode("utf-8", errors="replace")
                txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", txt)
                print("     ...", txt.replace("\n", " ")[:520])
