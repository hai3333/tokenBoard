#!/usr/bin/env python3
"""Decisive: are codex token_usage_record and event_msg/token_count the SAME requests?"""
import sys
import os
import json
import glob
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


for name_part in ("2026-10-13T08-30-04", "2026-10-09T09-08-34", "2026-10-16T15-07-08"):
    files = [f for f in glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True)
             if name_part in f]
    if not files:
        continue
    p = files[0]
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
                tur.append((parse_ts(o.get("timestamp")), u.get("input_tokens"),
                            u.get("cached_input_tokens"), u.get("output_tokens"),
                            u.get("total_tokens"), pl.get("response_id")))
            elif t == "event_msg" and pl.get("type") == "token_count":
                info = pl.get("info") or {}
                ltu = info.get("last_token_usage") or {}
                tc.append((parse_ts(o.get("timestamp")), ltu.get("input_tokens"),
                           ltu.get("cached_input_tokens"), ltu.get("output_tokens"),
                           ltu.get("total_tokens"), None))

    print("=" * 78)
    print(f"{name_part}   tur={len(tur)}  tokcnt={len(tc)}")
    print("=" * 78)
    if tur and tc:
        print(f"  tur   first={tur[0][0]} last={tur[-1][0]}  sum={sum(x[4] or 0 for x in tur):,}")
        print(f"  tc    first={tc[0][0]} last={tc[-1][0]}  sum={sum(x[4] or 0 for x in tc):,}")
        tur_ts = sorted(x[0] for x in tur if x[0])
        tc_ts = sorted(x[0] for x in tc if x[0])
        overlap = sum(1 for t in tur_ts if tc_ts and tc_ts[0] <= t <= tc_ts[-1])
        print(f"  tur records whose ts falls inside token_count window: {overlap}")
        # exact tuple match
        tset = {(x[1], x[2], x[3], x[4]) for x in tur}
        tset2 = {(x[1], x[2], x[3], x[4]) for x in tc}
        print(f"  identical (input,cached,output,total) tuples: "
              f"{len(tset & tset2)}  (tur-only={len(tset - tset2)}, tc-only={len(tset2 - tset)})")
        print("\n  first 5 tur:")
        for r in tur[:5]:
            print("    ", r)
        print("  first 5 tc:")
        for r in tc[:5]:
            print("    ", r)
        print("  last 3 tur:")
        for r in tur[-3:]:
            print("    ", r)
        print("  last 3 tc:")
        for r in tc[-3:]:
            print("    ", r)
    print()
