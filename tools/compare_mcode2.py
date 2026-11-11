#!/usr/bin/env python3
"""mcode：对比 input+output（不含缓存）—— 这才是可比口径。"""
import sys
import os
import sqlite3
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TB = os.path.join(os.environ["LOCALAPPDATA"], "TokenBoard", "tokenboard.db")
CC = os.path.expanduser("~/.cc-switch/cc-switch.db")

tb = sqlite3.connect(f"file:{TB}?mode=ro", uri=True)
tb.row_factory = sqlite3.Row
cc = sqlite3.connect(f"file:{CC}?mode=ro", uri=True)
cc.row_factory = sqlite3.Row

print(f"{'date':<12}{'TB n':>7}{'CC n':>7}   {'TB in+out':>16}{'CC in+out':>16}"
      f"{'偏差':>9}   {'TB cacheR':>16}{'CC cacheR':>16}")
agg = defaultdict(int)
days = sorted({r[0] for r in tb.execute(
    "select distinct day from usage_events where app='mcode'")})
for d in days:
    t = tb.execute(
        "select count(*) n, sum(input_tokens+output_tokens) io, sum(cache_read_tokens) cr "
        "from usage_events where app='mcode' and day=?", (d,)).fetchone()
    c = cc.execute(
        "select count(*) n, sum(input_tokens+output_tokens) io, sum(cache_read_tokens) cr "
        "from proxy_request_logs where app_type='mcode' and data_source='mcode_session' "
        "and date(created_at,'unixepoch','localtime')=?", (d,)).fetchone()
    if not c or not c["n"]:
        continue
    agg["tn"] += t["n"]; agg["cn"] += c["n"]
    agg["tio"] += t["io"] or 0; agg["cio"] += c["io"] or 0
    agg["tcr"] += t["cr"] or 0; agg["ccr"] += c["cr"] or 0
    diff = (t["io"] or 0) - (c["io"] or 0)
    print(f"{d:<12}{t['n']:>7}{c['n']:>7}   {t['io'] or 0:>16,}{c['io'] or 0:>16,}"
          f"{diff:>9,}   {t['cr'] or 0:>16,}{c['cr'] or 0:>16,}")
print("-" * 78)
print(f"{'合计':<12}{agg['tn']:>7}{agg['cn']:>7}   {agg['tio']:>16,}{agg['cio']:>16,}"
      f"{agg['tio'] - agg['cio']:>9,}   {agg['tcr']:>16,}{agg['ccr']:>16,}")
print(f"\n-> input+output 偏差 {agg['tio'] / agg['cio'] * 100 if agg['cio'] else 0:.2f}%"
      f"   缓存读偏差 {agg['tcr'] / agg['ccr'] * 100 if agg['ccr'] else 0:.2f}%")
