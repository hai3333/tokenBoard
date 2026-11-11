#!/usr/bin/env python3
"""对 2026-10-10 做独立核算：直接从原始 rollout 文件数，与 TB / CC Switch 对比。"""
import sys
import os
import json
import glob
import sqlite3
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")
DAY = "2026-10-10"
NEAR_MS = 10_000

TB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "TokenBoard", "tokenboard.db")
CC = os.path.join(HOME, ".cc-switch", "cc-switch.db")

print("=" * 84)
print(f"独立核算：{DAY} 从原始 rollout 文件直接统计")
print("=" * 84)

tur = []   # (ts, tuple)
tc = []
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
            if str(o.get("timestamp", ""))[:10] != DAY:
                # 按本地日期归并（rollout 用 UTC，TokenBoard 用本地时区）
                from datetime import datetime, timezone, timedelta
                try:
                    local_day = (datetime.fromisoformat(
                        str(o.get("timestamp")).replace("Z", "+00:00"))
                        + timedelta(hours=8)).strftime("%Y-%m-%d")
                except Exception:
                    continue
                if local_day != DAY:
                    continue
            t = o.get("type")
            pl = o.get("payload") or {}
            if not isinstance(pl, dict):
                continue
            if t == "token_usage_record":
                u = pl.get("usage") or {}
                i = int(u.get("input_tokens") or 0)
                c = int(u.get("cached_input_tokens") or 0)
                o_ = int(u.get("output_tokens") or 0)
                cw = int(u.get("cache_write_input_tokens") or 0)
                tur.append((o.get("timestamp"), (max(0, i - c), o_, c, cw)))
            elif t == "event_msg" and pl.get("type") == "token_count":
                u = (pl.get("info") or {}).get("last_token_usage") or {}
                i = int(u.get("input_tokens") or 0)
                c = int(u.get("cached_input_tokens") or 0)
                o_ = int(u.get("output_tokens") or 0)
                cw = int(u.get("cache_write_input_tokens") or 0)
                tc.append((o.get("timestamp"), (max(0, i - c), o_, c, cw)))

print(f"  原始文件里该日：token_usage_record = {len(tur)} 条, token_count = {len(tc)} 条")

# 按时间邻近配对去重
def ts_ms(s):
    from datetime import datetime
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)

by_tuple = defaultdict(list)
for s, k in tur:
    by_tuple[k].append(ts_ms(s))
for v in by_tuple.values():
    v.sort()

uniq_tc = 0
for s, k in tc:
    stamps = by_tuple.get(k) or []
    best_i, best_d = -1, NEAR_MS + 1
    for i, t in enumerate(stamps):
        d = abs(t - ts_ms(s))
        if d < best_d:
            best_d, best_i = d, i
    if best_i >= 0 and best_d <= NEAR_MS:
        stamps.pop(best_i)
    else:
        uniq_tc += 1

print(f"  去重后独立请求数 = {len(tur)} + {uniq_tc} = {len(tur) + uniq_tc}")

tb = sqlite3.connect(f"file:{TB}?mode=ro", uri=True)
r = tb.execute(
    "select count(*) n, sum(input_tokens) i, sum(output_tokens) o, sum(cache_read_tokens) cr "
    "from usage_events where app='codex' and day=?", (DAY,)).fetchone()
print(f"  TokenBoard      : n={r[0]}  in={r[1]} out={r[2]} cacheR={r[3]}")

cc = sqlite3.connect(f"file:{CC}?mode=ro", uri=True)
r2 = cc.execute(
    "select count(*) n, sum(input_tokens) i, sum(output_tokens) o, sum(cache_read_tokens) cr "
    "from proxy_request_logs where app_type='codex' and data_source='codex_session' "
    "and date(created_at,'unixepoch','localtime')=?", (DAY,)).fetchone()
print(f"  CC Switch       : n={r2[0]}  in={r2[1]} out={r2[2]} cacheR={r2[3]}")

print()
print("=" * 84)
print("CC Switch 自己的日志里有没有采集报错")
print("=" * 84)
log_dir = os.path.join(HOME, ".cc-switch", "logs")
for p in sorted(glob.glob(os.path.join(log_dir, "*.log")), key=os.path.getmtime)[-2:]:
    print(f"\n  -- {os.path.basename(p)}")
    with open(p, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    hits = [ln for ln in lines
            if any(k in ln.lower() for k in ("session_log", "sync", "error", "warn", "codex"))]
    for ln in hits[-18:]:
        print("    ", ln.rstrip()[:220])
