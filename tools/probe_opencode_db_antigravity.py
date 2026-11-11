#!/usr/bin/env python3
"""Probe opencode.db + antigravity transcripts for token usage."""
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
print("OPENCODE opencode.db schema")
print("=" * 72)
db = os.path.join(HOME, ".local/share/opencode/opencode.db")
if os.path.exists(db):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    objs = conn.execute("select type,name,sql from sqlite_master where type in ('table','view')").fetchall()
    for o in objs:
        low = o["name"].lower()
        hit = any(k in low for k in ("usage", "token", "cost", "message", "session", "part", "model"))
        try:
            n = conn.execute(f'select count(*) from "{o["name"]}"').fetchone()[0]
        except Exception:  # noqa: BLE001
            n = "?"
        print(f"\n-- {o['name']}  rows={n}{'   <== ' if hit else ''}")
        if hit:
            print(f"   {(o['sql'] or '')[:1200]}")
            if n and n != "?":
                try:
                    rows = conn.execute(f'select * from "{o["name"]}" limit 2').fetchall()
                except Exception:  # noqa: BLE001
                    continue
                for r in rows:
                    d = {k: (str(r[k])[:200] if r[k] is not None else None) for k in r.keys()}
                    print("     ", d)
    print("\n-- columns with token/usage/cost --")
    for o in conn.execute("select name from sqlite_master where type='table'").fetchall():
        try:
            cols = conn.execute(f'PRAGMA table_info("{o["name"]}")').fetchall()
        except Exception:  # noqa: BLE001
            continue
        for c in cols:
            if any(k in (c["name"] or "").lower() for k in ("token", "usage", "cost")):
                print(f"   {o['name']}.{c['name']} ({c['type']})")
else:
    print("  NOT FOUND")

print("\n" + "=" * 72)
print("ANTIGRAVITY transcripts")
print("=" * 72)
ag = os.path.join(HOME, ".gemini/antigravity/brain")
hits = 0
for p in sorted(glob.glob(os.path.join(ag, "**", "transcript*.jsonl"), recursive=True),
                key=os.path.getmtime, reverse=True)[:40]:
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception:  # noqa: BLE001
        continue
    if re.search(r"(input[_ ]?tokens|output[_ ]?tokens|total[_ ]?tokens|promptTokenCount)", txt, re.I):
        hits += 1
        if hits <= 2:
            print(f"\n  HIT {os.path.relpath(p, ag)}")
            for m in list(re.finditer(r"(input[_ ]?tokens|output[_ ]?tokens|total[_ ]?tokens|promptTokenCount|candidatesTokenCount|cachedContentTokenCount|usageMetadata)", txt, re.I))[:6]:
                s = max(0, m.start() - 250)
                print("     ", txt[s:m.start() + 300].replace("\n", " ")[:520])
print(f"\n  transcripts with token fields: {hits}")

print("\n" + "=" * 72)
print("ANTIGRAVITY conversation_summaries.db")
print("=" * 72)
cdb = os.path.join(HOME, ".gemini/antigravity/conversation_summaries.db")
if os.path.exists(cdb):
    conn = sqlite3.connect(f"file:{cdb}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    for o in conn.execute("select type,name,sql from sqlite_master where type='table'").fetchall():
        n = conn.execute(f'select count(*) from "{o["name"]}"').fetchone()[0]
        print(f"\n-- {o['name']} rows={n}")
        print(f"   {(o['sql'] or '')[:800]}")
        if n:
            for r in conn.execute(f'select * from "{o["name"]}" limit 1'):
                print("     ", {k: (str(r[k])[:250] if r[k] is not None else None) for k in r.keys()})
