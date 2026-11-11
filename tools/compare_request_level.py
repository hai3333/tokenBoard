#!/usr/bin/env python3
"""TokenBoard vs CC Switch proxy_request_logs（逐请求口径，最严格对照）。"""
import sys
import os
import sqlite3
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

TB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "TokenBoard", "tokenboard.db")
CC = os.path.join(HOME, ".cc-switch", "cc-switch.db")

tb = sqlite3.connect(f"file:{TB}?mode=ro", uri=True)
tb.row_factory = sqlite3.Row
cc = sqlite3.connect(f"file:{CC}?mode=ro", uri=True)
cc.row_factory = sqlite3.Row

for app, ds in (("claude", "session_log"), ("codex", "codex_session"),
                ("opencode", "opencode_session")):
    print("=" * 92)
    print(f"### {app}   （CC Switch data_source={ds}）")
    print("=" * 92)

    ccd = defaultdict(lambda: [0, 0, 0, 0])
    for r in cc.execute(
        "select date(created_at,'unixepoch','localtime') d, count(*) n, "
        "sum(input_tokens) i, sum(output_tokens) o, sum(cache_read_tokens) cr "
        "from proxy_request_logs where app_type=? and data_source=? group by d",
        (app, ds)
    ):
        ccd[r["d"]] = [r["n"], r["i"] or 0, r["o"] or 0, r["cr"] or 0]

    tbd = defaultdict(lambda: [0, 0, 0, 0])
    for r in tb.execute(
        "select day d, count(*) n, sum(input_tokens) i, sum(output_tokens) o, "
        "sum(cache_read_tokens) cr from usage_events where app=? group by d", (app,)
    ):
        tbd[r["d"]] = [r["n"], r["i"] or 0, r["o"] or 0, r["cr"] or 0]

    common = sorted(set(ccd) & set(tbd))
    if not common:
        print("   无重叠日期")
        print(f"   CC 独有日期数={len(ccd)}  TB 独有日期数={len(tbd)}")
        continue

    print(f"   {'日期':<12}{'CC req':>7}{'TB req':>8}{'差':>7}   "
          f"{'CC in':>13}{'TB in':>13}   {'CC cacheR':>14}{'TB cacheR':>14}")
    agg = defaultdict(int)
    for d in common:
        c, t = ccd[d], tbd[d]
        for k in range(4):
            agg["c" + str(k)] += c[k]
            agg["t" + str(k)] += t[k]
    for d in common[-10:]:
        c, t = ccd[d], tbd[d]
        print(f"   {d:<12}{c[0]:>7}{t[0]:>8}{t[0]-c[0]:>7}   "
              f"{c[1]:>13,}{t[1]:>13,}   {c[3]:>14,}{t[3]:>14,}")
    print(f"   {'共同日期合计':<12}{agg['c0']:>7}{agg['t0']:>8}{agg['t0']-agg['c0']:>7}   "
          f"{agg['c1']:>13,}{agg['t1']:>13,}   {agg['c3']:>14,}{agg['t3']:>14,}")
    print(f"   -> 请求数 {agg['t0']}/{agg['c0']} = {agg['t0']/agg['c0']*100:.1f}%   "
          f"input {agg['t1']/agg['c1']*100 if agg['c1'] else 0:.1f}%   "
          f"cacheR {agg['t3']/agg['c3']*100 if agg['c3'] else 0:.1f}%")
    print(f"   （CC 独有 {len(set(ccd)-set(tbd))} 天，TB 独有 {len(set(tbd)-set(ccd))} 天）")
    print()

print("=" * 92)
print("CC Switch proxy_request_logs 里 codex 的时间跨度（说明历史来自已被清理的会话文件）")
print("=" * 92)
for r in cc.execute(
    "select app_type, data_source, min(date(created_at,'unixepoch','localtime')) d0, "
    "max(date(created_at,'unixepoch','localtime')) d1, count(*) n, "
    "count(distinct date(created_at,'unixepoch','localtime')) days "
    "from proxy_request_logs group by app_type, data_source"
):
    print(f"   {r['app_type']:<10} {r['data_source']:<20} {r['d0']} ~ {r['d1']}  "
          f"n={r['n']:<6} 天数={r['days']}")
