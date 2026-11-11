#!/usr/bin/env python3
"""对照 CC Switch 的口径，验证 TokenBoard 采集的准确性。"""
import sys
import os
import sqlite3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

TB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "TokenBoard", "tokenboard.db")
CC = os.path.join(HOME, ".cc-switch", "cc-switch.db")

tb = sqlite3.connect(f"file:{TB}?mode=ro", uri=True)
tb.row_factory = sqlite3.Row
cc = sqlite3.connect(f"file:{CC}?mode=ro", uri=True)
cc.row_factory = sqlite3.Row

print("=" * 78)
print("TokenBoard (本插件)")
print("=" * 78)
for r in tb.execute(
    "select app, count(*) n, sum(input_tokens) i, sum(output_tokens) o, "
    "sum(cache_read_tokens) cr, sum(cache_write_tokens) cw, sum(cost_usd) c, "
    "count(distinct day) days from usage_events group by app order by app"
):
    print(f"  {r['app']:<10} n={r['n']:<6} days={r['days']:<4} "
          f"in={r['i'] or 0:>14,} out={r['o'] or 0:>12,} "
          f"cacheR={r['cr'] or 0:>14,} cost=${r['c'] or 0:.4f}")

print()
print("=" * 78)
print("CC Switch (参考口径)")
print("=" * 78)
for r in cc.execute(
    "select app_type, count(*) n, sum(input_tokens) i, sum(output_tokens) o, "
    "sum(cache_read_tokens) cr, count(distinct date) days "
    "from usage_daily_rollups where provider_id like '%session%' group by app_type"
):
    print(f"  {r['app_type']:<10} n={r['n']:<6} days={r['days']:<4} "
          f"in={r['i'] or 0:>14,} out={r['o'] or 0:>12,} cacheR={r['cr'] or 0:>14,}")

print()
print("=" * 78)
print("CC Switch 原始明细 proxy_request_logs（session 来源）")
print("=" * 78)
for r in cc.execute(
    "select app_type, data_source, count(*) n, sum(input_tokens) i, sum(output_tokens) o, "
    "sum(cache_read_tokens) cr, min(date(created_at,'unixepoch','localtime')) d0, "
    "max(date(created_at,'unixepoch','localtime')) d1 "
    "from proxy_request_logs group by app_type, data_source order by app_type"
):
    print(f"  {r['app_type']:<10} {r['data_source']:<20} n={r['n']:<6} "
          f"in={r['i'] or 0:>14,} out={r['o'] or 0:>12,} cacheR={r['cr'] or 0:>13,} "
          f"{r['d0']} ~ {r['d1']}")

print()
print("=" * 78)
print("TokenBoard 每日明细（按 app）")
print("=" * 78)
for r in tb.execute(
    "select app, day, count(*) n, sum(total_tokens) t, sum(input_tokens) i, "
    "sum(output_tokens) o, sum(cache_read_tokens) cr from usage_events "
    "group by app, day order by app, day desc"
):
    print(f"  {r['app']:<10} {r['day']}  n={r['n']:<5} total={r['t'] or 0:>12,} "
          f"in={r['i'] or 0:>11,} out={r['o'] or 0:>8,} cr={r['cr'] or 0:>12,}")

print()
print("=" * 78)
print("按模型 top 20（TokenBoard）")
print("=" * 78)
for r in tb.execute(
    "select app, model, count(*) n, sum(total_tokens) t from usage_events "
    "where model<>'' group by app, model order by t desc limit 20"
):
    print(f"  {r['app']:<10} {r['model']:<40} n={r['n']:<6} t={r['t'] or 0:>13,}")

print()
print("=== 模型为空的比例 ===")
for r in tb.execute(
    "select app, count(*) n, sum(case when model='' then 1 else 0 end) blank "
    "from usage_events group by app"
):
    print(f"  {r['app']:<10} n={r['n']:<6} 无模型={r['blank']}")
