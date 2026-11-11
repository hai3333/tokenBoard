#!/usr/bin/env python3
"""MiniMax Code 对照 CC Switch。"""
import sys
import os
import sqlite3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TB = os.path.join(os.environ["LOCALAPPDATA"], "TokenBoard", "tokenboard.db")
CC = os.path.expanduser("~/.cc-switch/cc-switch.db")

tb = sqlite3.connect(f"file:{TB}?mode=ro", uri=True)
tb.row_factory = sqlite3.Row
cc = sqlite3.connect(f"file:{CC}?mode=ro", uri=True)
cc.row_factory = sqlite3.Row

print("mcode 逐日对比 (TokenBoard vs CC Switch mcode_session)")
print("-" * 78)
print(f"{'date':<12}{'TB n':>7}{'CC n':>7}{'diff':>7}   {'TB total':>16}{'CC total':>16}")
agg = [0, 0, 0, 0]
days = sorted({r[0] for r in tb.execute(
    "select distinct day from usage_events where app='mcode'")})
for d in days:
    t = tb.execute(
        "select count(*) n, sum(total_tokens) t from usage_events "
        "where app='mcode' and day=?", (d,)).fetchone()
    c = cc.execute(
        "select count(*) n, sum(input_tokens+output_tokens) t from proxy_request_logs "
        "where app_type='mcode' and data_source='mcode_session' "
        "and date(created_at,'unixepoch','localtime')=?", (d,)).fetchone()
    if not c or not c["n"]:
        continue
    agg[0] += t["n"]; agg[1] += c["n"]
    agg[2] += t["t"] or 0; agg[3] += c["t"] or 0
    print(f"{d:<12}{t['n']:>7}{c['n']:>7}{t['n'] - c['n']:>7}   "
          f"{t['t'] or 0:>16,}{c['t'] or 0:>16,}")
print("-" * 78)
print(f"{'合计':<12}{agg[0]:>7}{agg[1]:>7}{agg[0] - agg[1]:>7}   "
      f"{agg[2]:>16,}{agg[3]:>16,}")
if agg[1]:
    print(f"-> 请求数 {agg[0]}/{agg[1]} = {agg[0] / agg[1] * 100:.1f}%   "
          f"总token {agg[2] / agg[3] * 100 if agg[3] else 0:.1f}%")
