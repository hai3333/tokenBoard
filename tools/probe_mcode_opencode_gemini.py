#!/usr/bin/env python3
"""Find token usage storage for MiniMax Code (mcode), OpenCode, Gemini CLI."""
import sys
import os
import glob
import json
import sqlite3
import re
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

print("=" * 72)
print("MCODE : ~/.minimax/v2/sqlite/runtime-state.sqlite")
print("=" * 72)
db = os.path.join(HOME, ".minimax/v2/sqlite/runtime-state.sqlite")
if os.path.exists(db):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    for o in conn.execute("select type,name,sql from sqlite_master where type in ('table','view')").fetchall():
        low = o["name"].lower()
        if not any(k in low for k in ("usage", "token", "message", "session", "request", "model")):
            continue
        try:
            n = conn.execute(f'select count(*) from "{o["name"]}"').fetchone()[0]
        except Exception:  # noqa: BLE001
            n = "?"
        print(f"\n-- {o['name']}  rows={n}")
        print(f"   {(o['sql'] or '')[:700]}")
        if n and n != "?":
            try:
                rows = conn.execute(f'select * from "{o["name"]}" limit 2').fetchall()
            except Exception:  # noqa: BLE001
                continue
            for r in rows:
                d = {k: (str(r[k])[:160] if r[k] is not None else None) for k in r.keys()}
                print("     ", d)
    print("\n-- tables containing 'token' column --")
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
print("OPENCODE : search for storage")
print("=" * 72)
for cand in (os.path.join(HOME, ".local/share/opencode"), os.path.join(HOME, ".config/opencode"),
             os.path.join(HOME, ".opencode"), os.path.join(HOME, ".local/state/opencode")):
    print(f"\n--- {cand} exists={os.path.exists(cand)}")
    if os.path.isdir(cand):
        for e in sorted(os.listdir(cand))[:25]:
            full = os.path.join(cand, e)
            print(f"     {'[D]' if os.path.isdir(full) else '[F]'} {e}"
                  + ("" if os.path.isdir(full) else f" ({os.path.getsize(full)})"))

print("\n" + "=" * 72)
print("GEMINI CLI : ~/.gemini")
print("=" * 72)
g = os.path.join(HOME, ".gemini")
if os.path.isdir(g):
    for root, dirs, files in os.walk(g):
        dirs[:] = [d for d in dirs if d not in ("node_modules",)]
        for f in files:
            p = os.path.join(root, f)
            try:
                sz = os.path.getsize(p)
            except Exception:  # noqa: BLE001
                continue
            print(f"   {os.path.relpath(p, g)}  ({sz})")
            if sz < 5 * 1024 * 1024 and f.endswith((".json", ".jsonl")):
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        txt = fh.read()
                except Exception:  # noqa: BLE001
                    continue
                if re.search(r"(input_tokens|output_tokens|total_tokens|promptTokenCount)", txt):
                    print("        >>> HAS TOKEN FIELDS")
                    for m in list(re.finditer(r"(input_tokens|output_tokens|total_tokens|promptTokenCount|candidatesTokenCount|cachedContentTokenCount)", txt))[:6]:
                        s = max(0, m.start() - 150)
                        print("        ", txt[s:m.start() + 260].replace("\n", " ")[:420])
