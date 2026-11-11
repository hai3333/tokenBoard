#!/usr/bin/env python3
"""统计 Codex 额度接口的失败率，判断是否需要重试。"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.quota import fetch_codex

ok = fail = 0
for i in range(8):
    t0 = time.time()
    r = fetch_codex()
    dt = (time.time() - t0) * 1000
    status = "OK " if r.get("ok") else "ERR"
    if r.get("ok"):
        ok += 1
    else:
        fail += 1
    print(f"{i + 1}. {status} {dt:6.0f}ms  {r.get('error', '')[:70]}")
    time.sleep(0.4)

print(f"\n成功 {ok} / 失败 {fail}")
