#!/usr/bin/env python3
"""Per-file: does codex rollout have token_usage_record vs event_msg/token_count? And model source."""
import sys
import os
import json
import glob
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")

files = sorted(glob.glob(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), recursive=True),
               key=os.path.getmtime, reverse=True)
print(f"{len(files)} files\n")
print(f"{'file':<46} {'tur':>5} {'tokcnt':>7} {'model':<28} {'sum_tur_total':>13} {'sum_tc_last':>12}")
for p in files[:30]:
    tur = 0
    tc = 0
    models = Counter()
    sum_tur = 0
    sum_tc = 0
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
                tur += 1
                u = pl.get("usage") or {}
                sum_tur += u.get("total_tokens") or 0
            elif t == "event_msg" and pl.get("type") == "token_count":
                tc += 1
                info = pl.get("info") or {}
                ltu = info.get("last_token_usage") or {}
                sum_tc += ltu.get("total_tokens") or 0
            elif t == "turn_context":
                m = pl.get("model")
                if m:
                    models[m] += 1
    name = os.path.basename(p)[:44]
    print(f"{name:<46} {tur:>5} {tc:>7} {str(models.most_common(1)): <28} {sum_tur:>13} {sum_tc:>12}")
