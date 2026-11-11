#!/usr/bin/env python3
"""Compare codex token_usage_record vs event_msg/token_count on one file."""
import sys
import os
import json
import glob

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

target = sys.argv[1] if len(sys.argv) > 1 else None
files = sorted(glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True),
               key=os.path.getmtime, reverse=True)
if target:
    files = [f for f in files if target in f]

for p in files[:1]:
    print(f"FILE {p}")
    tur, tc = [], []
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
            if t == "token_usage_record":
                u = pl.get("usage") or {}
                tur.append((o.get("ordinal"), o.get("timestamp"), pl.get("response_id"),
                            u.get("input_tokens"), u.get("cached_input_tokens"),
                            u.get("output_tokens"), u.get("total_tokens")))
            elif t == "event_msg" and pl.get("type") == "token_count":
                info = pl.get("info") or {}
                ltu = info.get("last_token_usage") or {}
                ttu = info.get("total_token_usage") or {}
                tc.append((o.get("ordinal"), o.get("timestamp"),
                           ltu.get("input_tokens"), ltu.get("cached_input_tokens"),
                           ltu.get("output_tokens"), ltu.get("total_tokens"),
                           ttu.get("total_tokens")))

    print(f"\ntoken_usage_record n={len(tur)}  sum_total={sum(x[6] or 0 for x in tur):,}")
    print(f"token_count        n={len(tc)}  sum_last={sum(x[5] or 0 for x in tc):,}")

    # duplicate detection in token_count
    seen = {}
    dup = 0
    for row in tc:
        k = (row[2], row[3], row[4], row[5])
        if k in seen:
            dup += 1
        seen[k] = seen.get(k, 0) + 1
    print(f"\ntoken_count duplicate (input,cached,output,total) tuples: {dup} "
          f"(of {len(tc)})")
    tc_cum = [r[6] for r in tc]
    mono = all(tc_cum[i] <= tc_cum[i + 1] for i in range(len(tc_cum) - 1))
    print(f"token_count total_token_usage monotonically non-decreasing: {mono}")
    if tc_cum:
        print(f"  first={tc_cum[0]:,} last={tc_cum[-1]:,}")

    print("\n--- first 12 token_count ---")
    for r in tc[:12]:
        print("   ", r)
    print("\n--- first 12 token_usage_record ---")
    for r in tur[:12]:
        print("   ", r)
