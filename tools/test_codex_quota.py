#!/usr/bin/env python3
"""单测 Codex 额度 provider。"""
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.quota import fetch_codex, fetch_all

r = fetch_codex()
print(json.dumps(r, ensure_ascii=False, indent=2))

print("\n--- 时间戳换算校验 ---")
for w in r.get("windows", []):
    rs = w["reset_at"] / 1000
    print(f"  {w['kind']}: used={w['used']:.1f}% remaining={w['remaining']:.1f}% "
          f"reset_at={time.strftime('%Y-%m-%d %H:%M', time.localtime(rs))} "
          f"(还有 {(rs - time.time()) / 3600:.1f} 小时)")

print("\n--- fetch_all 全量 ---")
for q in fetch_all():
    print(f"  {q.get('name')}: ok={q.get('ok')} "
          f"windows={len(q.get('windows') or [])} "
          f"err={q.get('error', '')[:60]}")
