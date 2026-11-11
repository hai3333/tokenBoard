#!/usr/bin/env python3
"""最终校验：TokenBoard vs 原始文件（tur 为唯一权威口径）。"""
import sys
import os
import json
import glob
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")
TZ = timedelta(hours=8)

TB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "TokenBoard", "tokenboard.db")
CC = os.path.join(HOME, ".cc-switch", "cc-switch.db")

# 原始文件：tur 是每响应唯一一条，口径无歧义
raw = defaultdict(lambda: {"n": 0, "tot": 0, "in": 0, "out": 0, "cr": 0})
for p in glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True):
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if o.get("type") != "token_usage_record":
                continue
            try:
                day = (datetime.fromisoformat(str(o.get("timestamp")).replace("Z", "+00:00"))
                       + TZ).strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                continue
            u = (o.get("payload") or {}).get("usage") or {}
            i = int(u.get("input_tokens") or 0)
            c = int(u.get("cached_input_tokens") or 0)
            o_ = int(u.get("output_tokens") or 0)
            r = raw[day]
            r["n"] += 1
            r["tot"] += int(u.get("total_tokens") or 0)
            r["in"] += max(0, i - c)
            r["out"] += o_
            r["cr"] += c

tb = sqlite3.connect(f"file:{TB}?mode=ro", uri=True)
cc = sqlite3.connect(f"file:{CC}?mode=ro", uri=True)

print("=" * 92)
print("codex 逐日：原始文件(tur 口径)  vs  TokenBoard  vs  CC Switch")
print("=" * 92)
print(f"   {'日期':<12}{'raw n':>7}{'TB n':>7}   {'raw total':>15}{'TB total':>15}"
      f"{'CC total':>15}   {'raw cacheR':>14}{'TB cacheR':>14}{'CC cacheR':>14}")
days = sorted(set(raw) & {r[0] for r in tb.execute(
    "select distinct day from usage_events where app='codex'")})
agg = defaultdict(int)
for d in days[-12:]:
    r = raw[d]
    t = tb.execute("select count(*) n, sum(total_tokens) t, sum(cache_read_tokens) cr "
                   "from usage_events where app='codex' and day=?", (d,)).fetchone()
    c = cc.execute("select count(*) n, sum(input_tokens+output_tokens) t, "
                   "sum(cache_read_tokens) cr from proxy_request_logs "
                   "where app_type='codex' and data_source='codex_session' "
                   "and date(created_at,'unixepoch','localtime')=?", (d,)).fetchone()
    agg["rn"] += r["n"]; agg["tn"] += t[0] or 0; agg["cn"] += c[0] or 0
    agg["rt"] += r["tot"]; agg["tt"] += t[1] or 0; agg["ct"] += c[1] or 0
    agg["rc"] += r["cr"]; agg["tc"] += t[2] or 0; agg["cc"] += c[2] or 0
    print(f"   {d:<12}{r['n']:>7}{t[0] or 0:>7}   {r['tot']:>15,}{t[1] or 0:>15,}"
          f"{c[1] or 0:>15,}   {r['cr']:>14,}{t[2] or 0:>14,}{c[2] or 0:>14,}")
print("-" * 92)
print(f"   {'合计':<12}{agg['rn']:>7}{agg['tn']:>7}   {agg['rt']:>15,}{agg['tt']:>15,}"
      f"{agg['ct']:>15,}   {agg['rc']:>14,}{agg['tc']:>14,}{agg['cc']:>14,}")
print()
print(f"   TokenBoard vs 原始文件(tur)：请求 {agg['tn']}/{agg['rn']} = "
      f"{agg['tn']/agg['rn']*100 if agg['rn'] else 0:.1f}%   "
      f"总 token {agg['tt']/agg['rt']*100 if agg['rt'] else 0:.1f}%   "
      f"缓存读 {agg['tc']/agg['rc']*100 if agg['rc'] else 0:.1f}%")
print(f"   CC Switch  vs 原始文件(tur)：请求 {agg['cn']}/{agg['rn']} = "
      f"{agg['cn']/agg['rn']*100 if agg['rn'] else 0:.1f}%   "
      f"总 token {agg['ct']/agg['rt']*100 if agg['rt'] else 0:.1f}%   "
      f"缓存读 {agg['cc']/agg['rc']*100 if agg['rc'] else 0:.1f}%")
