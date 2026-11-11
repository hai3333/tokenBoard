#!/usr/bin/env python3
import sqlite3
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = os.path.expanduser("~/.cc-switch/cc-switch.db")
c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("--- providers by app_type ---")
for r in c.execute("select app_type, count(*) n from providers group by app_type"):
    print(f"  {r['app_type']:<14} {r['n']}")

print("\n--- provider list ---")
for r in c.execute(
    "select app_type, name, is_current, provider_type, category from providers "
    "order by app_type, name"
):
    print(f"  {r['app_type']:<14} {r['name']:<32} cur={r['is_current']} type={r['provider_type']}")

print("\n--- model_pricing sample (token-cost rows) ---")
for r in c.execute(
    "select model_id, display_name, input_cost_per_million, output_cost_per_million, "
    "cache_read_cost_per_million from model_pricing limit 12"
):
    print(f"  {r['model_id']:<34} in={r['input_cost_per_million']:<10} out={r['output_cost_per_million']:<10} cr={r['cache_read_cost_per_million']}")

print("\n--- model_pricing: which vendors covered ---")
import re
c2 = c.execute("select model_id from model_pricing").fetchall()
pref = {}
for r in c2:
    mid = (r["model_id"] or "").lower()
    key = mid.split("-")[0].split("/")[0]
    pref[key] = pref.get(key, 0) + 1
for k, v in sorted(pref.items(), key=lambda kv: -kv[1])[:25]:
    print(f"  {k:<28} {v}")

print("\n--- pricing rows matching deepseek/glm/qwen/minimax/kimi ---")
for r in c.execute(
    "select model_id, input_cost_per_million, output_cost_per_million, cache_read_cost_per_million "
    "from model_pricing where lower(model_id) like '%deepseek%' or lower(model_id) like '%glm%' "
    "or lower(model_id) like '%qwen%' or lower(model_id) like '%minimax%' or lower(model_id) like '%kimi%'"
):
    print(f"  {r['model_id']:<40} {r['input_cost_per_million']:<10} {r['output_cost_per_million']:<10} {r['cache_read_cost_per_million']}")
