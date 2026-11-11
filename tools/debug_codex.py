#!/usr/bin/env python3
"""调试 Codex 采集：逐文件逐日统计，并寻找其他 codex 会话目录。"""
import sys
import os
import json
import glob
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "TokenBoard", "tokenboard.db")
db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

print("=" * 84)
print("TokenBoard 里的 codex 记录：按天")
print("=" * 84)
for r in db.execute(
    "select day, count(*) n, sum(input_tokens) i, sum(cache_read_tokens) cr "
    "from usage_events where app='codex' group by day order by day"
):
    print(f"   {r['day']}  n={r['n']:<5} in={r['i'] or 0:>12,} cr={r['cr'] or 0:>12,}")

print()
print("=" * 84)
print("直接跑 CodexCollector，按文件统计产出")
print("=" * 84)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tokenboard.collectors.codex import CodexCollector  # noqa: E402
from tokenboard.store import Store  # noqa: E402

store = Store(os.path.join(os.environ["TEMP"], "tb_debug.sqlite"))
col = CodexCollector(store)
files = sorted(glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True))
for p in files[:6]:
    recs = col._parse_file(p)
    days = defaultdict(int)
    for r in recs:
        days[datetime.fromtimestamp(r.ts_ms / 1000).strftime("%Y-%m-%d")] += 1
    print(f"\n  {os.path.basename(p)[:60]}")
    print(f"    -> 解析出 {len(recs)} 条，覆盖 {len(days)} 天")
    for d in sorted(days)[:6]:
        print(f"       {d}: {days[d]}")

print()
print("=" * 84)
print("原始文件里 event_msg/token_count 与 token_usage_record 的逐日分布（对照）")
print("=" * 84)
for p in files[:3]:
    tur_d, tc_d = Counter(), Counter()
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            t = o.get("type")
            pl = o.get("payload") or {}
            if not isinstance(pl, dict):
                continue
            day = str(o.get("timestamp", ""))[:10]
            if t == "token_usage_record":
                tur_d[day] += 1
            elif t == "event_msg" and pl.get("type") == "token_count":
                tc_d[day] += 1
    print(f"\n  {os.path.basename(p)[:60]}")
    print(f"    tur 按天: {dict(sorted(tur_d.items()))[:8]}")
    print(f"    tc  按天: {dict(sorted(tc_d.items()))[:8]}")

print()
print("=" * 84)
print("其它可能的 codex 会话目录")
print("=" * 84)
for cand in (os.path.join(HOME, "AppData/Roaming/Codex"),
             os.path.join(HOME, "AppData/Local/OpenAI/Codex"),
             os.path.join(HOME, "AppData/Roaming/OpenAI/Codex"),
             os.path.join(HOME, ".codex")):
    if not os.path.isdir(cand):
        print(f"  [无] {cand}")
        continue
    print(f"  {cand}")
    for root, dirs, files in os.walk(cand):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "bin", "runtimes", "skills", "plugins")]
        for f in files:
            if f.endswith((".jsonl", ".db", ".sqlite")):
                fp = os.path.join(root, f)
                try:
                    print(f"      {os.path.relpath(fp, cand)}  ({os.path.getsize(fp):,})")
                except OSError:
                    pass
