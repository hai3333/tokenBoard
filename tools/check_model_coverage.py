#!/usr/bin/env python3
"""检查库里 model 字段的覆盖率与去重情况（按模型汇总的前提）。"""
import sys
import os
import sqlite3
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TB = os.path.join(os.environ["LOCALAPPDATA"], "TokenBoard", "tokenboard.db")

conn = sqlite3.connect(f"file:{TB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("=" * 78)
print("model 字段覆盖率")
print("=" * 78)
for r in conn.execute(
    "select app, count(*) n, sum(case when model='' then 1 else 0 end) blank, "
    "count(distinct model) distinct_models, sum(total_tokens) t "
    "from usage_events group by app order by app"
):
    cov = (r["n"] - r["blank"]) / r["n"] * 100 if r["n"] else 0
    print(f"  {r['app']:<10} {r['n']:>6} 条   无模型 {r['blank']:>6} "
          f"({cov:5.1f}% 有模型)   去重模型数 {r['distinct_models']:>4}")

print()
print("=" * 78)
print("全部去重模型（按 token 排序）")
print("=" * 78)
rows = conn.execute(
    "select model, count(*) n, sum(total_tokens) t, group_concat(distinct app) apps "
    "from usage_events where model<>'' group by model order by t desc"
).fetchall()
print(f"  共 {len(rows)} 个不同模型字符串")
for r in rows:
    print(f"  {r['model']:<44} {r['n']:>6} 条  {r['t']/1e6:>10.1f}M   [{r['apps']}]")

print()
print("=" * 78)
print("去掉厂商前缀后能合并的模型")
print("=" * 78)
groups = {}
for r in rows:
    key = r["model"].split("/")[-1].lower()
    groups.setdefault(key, []).append((r["model"], r["n"], r["t"]))
merged = {k: v for k, v in groups.items() if len(v) > 1}
print(f"  原始 {len(rows)} 个 -> 归一后 {len(groups)} 个（合并掉 {len(merged)} 组）")
for k, v in sorted(merged.items()):
    print(f"  {k}:")
    for m, n, t in v:
        print(f"      {m:<44} {n:>6} 条 {t/1e6:>10.1f}M")
