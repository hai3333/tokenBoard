#!/usr/bin/env python3
"""Inspect how cc-switch ingests usage: session log paths + data_source split."""
import os
import re
import sqlite3
from collections import Counter

DB = os.path.expanduser("~/.cc-switch/cc-switch.db")


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("proxy_request_logs: app_type x data_source")
    print("=" * 70)
    for r in conn.execute(
        "select app_type, data_source, count(*) n, "
        "min(date(created_at,'unixepoch','localtime')) d0, "
        "max(date(created_at,'unixepoch','localtime')) d1, "
        "sum(input_tokens) i, sum(output_tokens) o "
        "from proxy_request_logs group by app_type, data_source order by app_type"
    ):
        print(dict(r))

    print("\n" + "=" * 70)
    print("usage_daily_rollups: app_type x provider_id")
    print("=" * 70)
    for r in conn.execute(
        "select app_type, provider_id, count(*) days, "
        "sum(input_tokens) i, sum(output_tokens) o, sum(cache_read_tokens) cr "
        "from usage_daily_rollups group by app_type, provider_id order by app_type"
    ):
        print(dict(r))

    print("\n" + "=" * 70)
    print("session_log_sync: path prefixes tracked")
    print("=" * 70)
    c = Counter()
    for r in conn.execute("select file_path from session_log_sync"):
        p = r["file_path"] or ""
        # normalize to app root
        m = re.match(r"^([A-Za-z]:\\[^\\]+(?:\\[^\\]+)?)", p)
        c[m.group(1) if m else p[:60]] += 1
    for k, v in c.most_common():
        print(f"{v:>6}  {k}")

    print("\n--- one sample path per prefix ---")
    seen = set()
    for r in conn.execute("select file_path from session_log_sync"):
        p = r["file_path"] or ""
        m = re.match(r"^([A-Za-z]:\\[^\\]+(?:\\[^\\]+)?)", p)
        k = m.group(1) if m else p[:60]
        if k not in seen:
            seen.add(k)
            print(f"  {p}")

    print("\n" + "=" * 70)
    print("settings table")
    print("=" * 70)
    for r in conn.execute("select key, substr(value,1,300) v from settings"):
        print(f"  {r['key']} = {r['v']}")

    print("\n" + "=" * 70)
    print("models seen in usage_daily_rollups")
    print("=" * 70)
    for r in conn.execute(
        "select app_type, model, count(*) n from usage_daily_rollups "
        "group by app_type, model order by app_type, n desc"
    ):
        print(f"  {r['app_type']:<12} {r['model']:<40} {r['n']}")


if __name__ == "__main__":
    main()
