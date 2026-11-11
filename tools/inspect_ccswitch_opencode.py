#!/usr/bin/env python3
"""看 ccswitch 里 opencode provider 的 settings_config 长什么样（密钥脱敏）。"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = os.path.expandvars(r"%USERPROFILE%\.cc-switch\cc-switch.db")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

SECRET = ("apikey", "api_key", "key", "token", "secret", "password", "auth")


def mask(obj, path=""):
    """把疑似密钥的值换成 <加密/明文 标记 + 长度>。"""
    if isinstance(obj, dict):
        return {k: mask(v, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask(v, path) for v in obj]
    if isinstance(obj, str) and len(obj) > 12:
        looks_enc = any(c in obj for c in ("�", "==")) or not obj.isprintable()
        return f"<{'疑似密文' if looks_enc else '明文'} {len(obj)}字符>"
    return obj


print("=== providers 里 app_type 分布 ===")
for row in cur.execute("SELECT app_type, COUNT(*) FROM providers GROUP BY app_type"):
    print("  ", row)

print("\n=== opencode 相关 provider ===")
rows = cur.execute(
    "SELECT id, name, is_current, settings_config, meta, provider_type "
    "FROM providers WHERE app_type LIKE '%opencode%'").fetchall()
for pid, name, cur_flag, cfg, meta, ptype in rows:
    print(f"\n-- id={pid} name={name!r} is_current={cur_flag} provider_type={ptype}")
    for label, blob in (("settings_config", cfg), ("meta", meta)):
        try:
            obj = json.loads(blob) if blob else None
        except Exception:  # noqa: BLE001
            print(f"   {label}: <非 JSON> {str(blob)[:80]}")
            continue
        if obj is None:
            print(f"   {label}: None")
            continue
        print(f"   {label}:")
        print("     " + json.dumps(mask(obj), ensure_ascii=False, indent=2)[:2000])

print("\n=== settings 表 ===")
for k, v in cur.execute("SELECT key, value FROM settings"):
    vv = str(v)
    if len(vv) > 120:
        vv = vv[:120] + "..."
    print(f"  {k} = {vv}")

con.close()
