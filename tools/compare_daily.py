#!/usr/bin/env python3
"""逐日对照 TokenBoard 与 CC Switch，验证采集准确性。"""
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

# app -> ccswitch 的 provider_id
CC_PID = {"claude": "_session", "codex": "_codex_session", "opencode": "_opencode_session"}

print("=" * 92)
print("逐日对照（CC Switch usage_daily_rollups  vs  TokenBoard usage_events）")
print("=" * 92)
for app, pid in CC_PID.items():
    ccd = defaultdict(lambda: [0, 0, 0, 0])   # day -> [req, input, output, cacheR]
    for r in cc.execute(
        "select date, sum(request_count) req, sum(input_tokens) i, sum(output_tokens) o, "
        "sum(cache_read_tokens) cr from usage_daily_rollups "
        "where app_type=? and provider_id=? group by date", (app, pid)
    ):
        ccd[r["date"]] = [r["req"] or 0, r["i"] or 0, r["o"] or 0, r["cr"] or 0]

    tbd = defaultdict(lambda: [0, 0, 0, 0])
    for r in tb.execute(
        "select day, count(*) req, sum(input_tokens) i, sum(output_tokens) o, "
        "sum(cache_read_tokens) cr from usage_events where app=? group by day", (app,)
    ):
        tbd[r["day"]] = [r["req"], r["i"] or 0, r["o"] or 0, r["cr"] or 0]

    common = sorted(set(ccd) & set(tbd))
    print(f"\n### {app}   CC Switch 天数={len(ccd)}  TokenBoard 天数={len(tbd)}  "
          f"共同天数={len(common)}")
    if not common:
        print("   （无重叠日期）")
        continue

    print(f"   {'日期':<12}{'CC req':>7}{'TB req':>8}   {'CC in':>13}{'TB in':>13}   "
          f"{'CC out':>9}{'TB out':>9}   {'CC cacheR':>13}{'TB cacheR':>13}")
    show = common[-8:]
    agg = [0, 0, 0, 0, 0, 0, 0, 0]
    for d in common:
        c = ccd[d]
        t = tbd[d]
        agg[0] += c[0]; agg[1] += t[0]
        agg[2] += c[1]; agg[3] += t[1]
        agg[4] += c[2]; agg[5] += t[2]
        agg[6] += c[3]; agg[7] += t[3]
    for d in show:
        c = ccd[d]
        t = tbd[d]
        print(f"   {d:<12}{c[0]:>7}{t[0]:>8}   {c[1]:>13,}{t[1]:>13,}   "
              f"{c[2]:>9,}{t[2]:>9,}   {c[3]:>13,}{t[3]:>13,}")
    print(f"   {'合计':<12}{agg[0]:>7}{agg[1]:>8}   {agg[2]:>13,}{agg[3]:>13,}   "
          f"{agg[4]:>9,}{agg[5]:>9,}   {agg[6]:>13,}{agg[7]:>13,}")
    if agg[0]:
        print(f"   -> request 覆盖率 {agg[1]/agg[0]*100:.1f}%  "
              f"input 覆盖率 {agg[3]/agg[2]*100 if agg[2] else 0:.1f}%  "
              f"cacheR 覆盖率 {agg[7]/agg[6]*100 if agg[6] else 0:.1f}%")

print("\n" + "=" * 92)
print("CC Switch 未被本插件覆盖的日期（有 CC 无 TB）")
print("=" * 92)
for app, pid in CC_PID.items():
    cc_days = {r["date"] for r in cc.execute(
        "select distinct date from usage_daily_rollups where app_type=? and provider_id=?",
        (app, pid))}
    tb_days = {r["day"] for r in tb.execute(
        "select distinct day from usage_events where app=?", (app,))}
    only_cc = sorted(cc_days - tb_days)
    print(f"  {app:<10} 仅 CC 有 {len(only_cc)} 天  范围: "
          f"{only_cc[0] if only_cc else '-'} ~ {only_cc[-1] if only_cc else '-'}")
