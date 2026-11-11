#!/usr/bin/env python3
"""看 CC Switch 里 provider 配置的结构（**只打印键名，不打印密钥**）。"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def redact(obj, depth=0):
    """把疑似密钥的值替换成 <len:N>，只留结构。"""
    if isinstance(obj, dict):
        return {k: redact(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, depth + 1) for v in obj[:6]]
    if isinstance(obj, str):
        low = obj.lower()
        if any(k in low for k in ("sk-", "key", "token", "secret", "password")):
            return f"<redacted len={len(obj)}>"
        if len(obj) > 60:
            return f"<str len={len(obj)}>"
        return obj
    return obj


cc = sqlite3.connect(f"file:{os.path.expanduser('~/.cc-switch/cc-switch.db')}?mode=ro",
                     uri=True)
cc.row_factory = sqlite3.Row

print("=" * 76)
print("provider 配置结构（按名称找火山 / minimax / 订阅相关）")
print("=" * 76)
for r in cc.execute("select id, app_type, name, settings_config, meta from providers "
                    "order by app_type, name"):
    try:
        cfg = json.loads(r["settings_config"])
    except Exception:  # noqa: BLE001
        cfg = {"<raw>": r["settings_config"][:100]}
    print(f"\n--- {r['app_type']} / {r['name']}  (id={r['id']}) ---")
    print("  settings_config:", json.dumps(redact(cfg), ensure_ascii=False)[:900])
    try:
        meta = json.loads(r["meta"] or "{}")
    except Exception:  # noqa: BLE001
        meta = {}
    if meta:
        print("  meta:", json.dumps(redact(meta), ensure_ascii=False)[:400])

print()
print("=" * 76)
print("定价表里跟订阅/套餐相关的行")
print("=" * 76)
for r in cc.execute("select * from model_pricing limit 0"):
    pass
print("（略）")
