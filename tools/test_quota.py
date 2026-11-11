#!/usr/bin/env python3
"""额度采集自检。"""
import datetime
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tokenboard import quota

for r in quota.fetch_all():
    print(f"--- {r['name']}  ok={r['ok']}  err={r.get('error', '')}")
    if r.get("hint"):
        print(f"    提示: {r['hint']}")
    for w in r["windows"]:
        rs = (datetime.datetime.fromtimestamp(w["reset_at"] / 1000)
              .strftime("%m-%d %H:%M") if w["reset_at"] else "-")
        print(f"    {w['kind']:<7} 剩余 {w['remaining']:5.1f}%  "
              f"已用 {w['used']:5.1f}%  重置 {rs}  无限={w['unlimited']}")
