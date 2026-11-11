#!/usr/bin/env python3
"""查看 cc-switch.db 的结构（只看结构，不打印密钥明文）。"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = os.path.expandvars(r"%USERPROFILE%\.cc-switch\cc-switch.db")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

print("=== 表 ===")
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
for t in tables:
    print(" -", t)

for t in tables:
    cols = cur.execute(f"PRAGMA table_info({t})").fetchall()
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"\n=== {t}（{n} 行） ===")
    print("  ", ", ".join(f"{c[1]}:{c[2]}" for c in cols))

print("\n=== providers 表内容概览（隐去密钥字段） ===")
if "providers" in tables:
    cols = [c[1] for c in cur.execute("PRAGMA table_info(providers)")]
    print("  列:", cols)
    secret_ish = ("key", "secret", "token", "credential")
    for row in cur.execute("SELECT * FROM providers"):
        d = dict(zip(cols, row))
        for k in list(d):
            if any(s in k.lower() for s in secret_ish):
                v = d[k]
                d[k] = f"<{len(str(v))}字符>" if v else v
        # config/settings 这类 JSON 字段只看键名
        for k in list(d):
            if isinstance(d[k], str) and d[k][:1] in "{[":
                try:
                    obj = json.loads(d[k])
                    d[k] = f"<json: {list(obj)[:8]}>" if isinstance(obj, dict) else "<json>"
                except Exception:  # noqa: BLE001
                    d[k] = "<非 JSON 字符串>"
        print("  ", d)

print("\n=== 其他表里的 app_type 分布 ===")
for t in tables:
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
    if "app_type" in cols:
        rows = cur.execute(f"SELECT app_type, COUNT(*) FROM {t} GROUP BY app_type").fetchall()
        print(f"  {t}: {rows}")

con.close()
