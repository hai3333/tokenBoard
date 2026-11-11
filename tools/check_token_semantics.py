#!/usr/bin/env python3
"""确认各家 total_tokens 口径差异 —— 决定归一化方式。"""
import sys
import os
import json
import glob
import sqlite3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

print("=" * 78)
print("CODEX: total_tokens 是否 = input + output (即 input 已含 cached)")
print("=" * 78)
files = sorted(glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True),
               key=os.path.getmtime, reverse=True)
n = 0
ok_incl = ok_excl = 0
for p in files[:4]:
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
            u = (o.get("payload") or {}).get("usage") or {}
            i, c, o_, t = (u.get("input_tokens"), u.get("cached_input_tokens"),
                           u.get("output_tokens"), u.get("total_tokens"))
            if None in (i, c, o_, t):
                continue
            n += 1
            if t == i + o_:
                ok_incl += 1
            if t == i - c + o_ + c:
                ok_excl += 1
            if n <= 4:
                print(f"   input={i:>9,} cached={c:>9,} output={o_:>6,} total={t:>9,}"
                      f"   input+output={i+o_:>9,}  (input-cached)+output+cached={i-c+o_+c:>9,}")
print(f"   -> {n} 条中 input+output==total 的有 {ok_incl} 条  (说明 input 已含 cached)")

print()
print("=" * 78)
print("CLAUDE: input 是否不含 cache")
print("=" * 78)
n = ok_excl = 0
for p in sorted(glob.glob(os.path.join(HOME, ".claude/projects/**/*.jsonl"), recursive=True),
                key=os.path.getmtime, reverse=True)[:3]:
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            try:
                o = json.loads(ln.strip())
            except Exception:  # noqa: BLE001
                continue
            if o.get("type") != "assistant":
                continue
            u = (o.get("message") or {}).get("usage")
            if not isinstance(u, dict):
                continue
            i, c, cw, ou = (u.get("input_tokens", 0), u.get("cache_read_input_tokens", 0),
                            u.get("cache_creation_input_tokens", 0), u.get("output_tokens", 0))
            if i + ou + c + cw == 0:
                continue
            n += 1
            if n <= 4:
                print(f"   input={i:>8,} cacheR={c:>9,} cacheW={cw:>6,} output={ou:>6,}"
                      f"  合计={i+c+cw+ou:>10,}")
print(f"   -> Anthropic 口径：input 不含 cache，总量 = input+cacheR+cacheW+output")

print()
print("=" * 78)
print("MCODE: raw 里 totalTokens 的构成 + effectiveModel")
print("=" * 78)
db = os.path.join(HOME, ".minimax/v2/sqlite/runtime-state.sqlite")
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
for r in conn.execute(
    "select id, session_id, model, ts, input_tokens, output_tokens, cache_read_tokens, "
    "cache_write_tokens, raw from local_runtime_token_usage order by id desc limit 3"
):
    print(f"   id={r['id']} model={r['model']!r}")
    print(f"     raw={r['raw']}")
print("   -- sessions 表里的 effectiveModel --")
for r in conn.execute(
    "select session_id, extra_data_json from local_runtime_sessions "
    "where extra_data_json like '%effectiveModel%' limit 3"
):
    try:
        d = json.loads(r["extra_data_json"])
    except Exception:  # noqa: BLE001
        d = {}
    print(f"     {r['session_id']} -> effectiveModel={d.get('effectiveModel')!r}")
