#!/usr/bin/env python3
"""核对用户真实 opencode.jsonc 与 TokenBoard 库里 provider 的一致性。

文件被改过（格式变了），这里确认**语义**没丢：
provider 集合 / 名称 / 密钥长度 / 模型数 / 全局默认模型。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = Path.home() / ".config/opencode/opencode.jsonc"
DB = Path.home() / "AppData/Local/TokenBoard/tokenboard.db"

raw = P.read_text(encoding="utf-8")
s = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
s = re.sub(r",(\s*[}\]])", r"\1", s)
cfg = json.loads(s)

print(f"文件: {P}  {len(raw)} 字节")
print("顶层键:", list(cfg.keys()))
print("model =", cfg.get("model"))
print("\n文件里的 provider:")
for pid, pv in cfg.get("provider", {}).items():
    o = pv.get("options", {})
    key = o.get("apiKey", "")
    print(f"  {pid:<8} name={pv.get('name', ''):<16} "
          f"key={key[:6]}...({len(key)}字) models={len(pv.get('models', {}))} "
          f"baseURL={o.get('baseURL', '')}")

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, name, api_key_enc, models_json, base_url FROM oc_providers"
    " ORDER BY sort_index").fetchall()
print("\nTokenBoard 库里的 provider:")
for r in rows:
    try:
        m = json.loads(r["models_json"] or "{}")
    except Exception:  # noqa: BLE001
        m = {}
    print(f"  {r['id']:<8} name={r['name']:<16} "
          f"key_enc={len(r['api_key_enc'] or '')}字 models={len(m)} "
          f"baseURL={r['base_url']}")

file_ids = set(cfg.get("provider", {}).keys())
db_ids = {r["id"] for r in rows}
print("\n对比：")
print("  文件独有:", sorted(file_ids - db_ids) or "无")
print("  库独有  :", sorted(db_ids - file_ids) or "无")
print("  provider 集合一致:", file_ids == db_ids)
print("  全局默认模型:", cfg.get("model"))
meta = conn.execute("SELECT value FROM oc_meta WHERE key='default_model'").fetchone()
print("  库里的默认模型:", meta["value"] if meta else "(空)")
