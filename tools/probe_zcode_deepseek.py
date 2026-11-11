#!/usr/bin/env python3
"""Reverse-engineer ZCode and DeepSeek (dsh-desktop) token usage storage."""
import json
import os
import glob
import sqlite3
import re
from collections import Counter

HOME = os.path.expanduser("~")


def dump_jsonl(path, label, maxlines=200):
    print(f"\n{'='*70}\n### {label} :: {path}\n{'='*70}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[:maxlines]
    except Exception as e:  # noqa: BLE001
        print("  ERR", e)
        return
    keys = Counter()
    hits = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(o, dict):
            continue
        keys.update(o.keys())
        s = json.dumps(o, ensure_ascii=False).lower()
        for kw in ("token", "usage", "cost"):
            if kw in s:
                hits.append(o)
                break
    print("  keys:", dict(keys.most_common(12)))
    print(f"  token/usage/cost-bearing lines: {len(hits)}")
    for o in hits[:3]:
        t = json.dumps(o, ensure_ascii=False)
        print("  ---", t[:900])


def dump_sqlite(path, label, tables_filter=None):
    print(f"\n{'='*70}\n### {label} :: {path}\n{'='*70}")
    if not os.path.exists(path):
        print("  NOT FOUND")
        return
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        objs = conn.execute(
            "select type,name,sql from sqlite_master where type in ('table','view')"
        ).fetchall()
    except Exception as e:  # noqa: BLE001
        print("  ERR", e)
        return
    for o in objs:
        low = o["name"].lower()
        if tables_filter and not any(k in low for k in tables_filter):
            continue
        try:
            n = conn.execute(f'select count(*) from "{o["name"]}"').fetchone()[0]
        except Exception:  # noqa: BLE001
            n = "?"
        print(f"\n-- [{o['type']}] {o['name']}  rows={n}")
        print(f"   {(o['sql'] or '')[:900]}")
        if n and n != "?" and n < 100000:
            try:
                rows = conn.execute(f'select * from "{o["name"]}" limit 2').fetchall()
            except Exception:  # noqa: BLE001
                continue
            for r in rows:
                d = {k: (str(r[k])[:150] if r[k] is not None else None) for k in r.keys()}
                print("     ", d)


if __name__ == "__main__":
    print("########## ZCODE model-io rollouts ##########")
    files = sorted(glob.glob(os.path.join(HOME, ".zcode/cli/rollout/*.jsonl")),
                   key=os.path.getmtime, reverse=True)
    for p in files[:2]:
        dump_jsonl(p, "zcode model-io")

    print("\n\n########## ZCODE cli db ##########")
    dump_sqlite(os.path.join(HOME, ".zcode/cli/db/db.sqlite"), "zcode cli db")

    print("\n\n########## ZCODE tasks-index ##########")
    dump_sqlite(os.path.join(HOME, ".zcode/v2/tasks-index.sqlite"), "zcode tasks-index",
                tables_filter=("usage", "token", "session", "message", "task", "model", "stat"))

    print("\n\n########## DEEPSEEK dsh-desktop ##########")
    ds = os.path.join(HOME, "AppData/Roaming/@deepseek-ai/dsh-desktop")
    for sub in ("logs", "desktop"):
        d = os.path.join(ds, sub)
        if not os.path.isdir(d):
            continue
        print(f"\n--- dsh-desktop/{sub} ---")
        for e in sorted(os.listdir(d))[:30]:
            full = os.path.join(d, e)
            sz = os.path.getsize(full) if os.path.isfile(full) else "-"
            print(f"   [{'D' if os.path.isdir(full) else 'F'}] {e} ({sz})")
