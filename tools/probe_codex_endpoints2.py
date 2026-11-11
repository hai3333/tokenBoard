#!/usr/bin/env python3
"""定向扫描 codex.exe：
1. backend-api 下的具体路径
2. x-codex-* 响应头名（速率限制通过响应头下发）
3. 额度/限额相关 JSON 字段名
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXE = os.path.expanduser("~/.codex/plugins/.plugin-appserver/codex.exe")

str_re = re.compile(rb"[\x20-\x7e]{4,400}")

paths = set()
headers = set()
jsonfields = set()

PATHS = re.compile(r"backend-api/[A-Za-z0-9/_.\-{}$]+")
HDRS = re.compile(r"x-codex-[a-z0-9\-]+")
FIELDS = re.compile(
    r"\b(rate_limits|rateLimitSnapshot|usedPercent|windowDurationMins|resetsAt|"
    r"primary|secondary|limitId|limitName|normalModelSlug|individualLimit|"
    r"plan_type|planType|subscription_plan|credits_balance|remaining_credits|"
    r"resets_at_seconds|reset_after_seconds)\b")

chunk = 8 * 1024 * 1024
tail = b""
with open(EXE, "rb") as f:
    while True:
        buf = f.read(chunk)
        if not buf:
            break
        buf = tail + buf
        for m in str_re.finditer(buf):
            s = m.group().decode("ascii", "replace")
            for p in PATHS.findall(s):
                paths.add(p)
            for h in HDRS.findall(s):
                headers.add(h)
            if FIELDS.search(s):
                jsonfields.add(s[:220])
        tail = buf[-600:]

print("=== backend-api 路径 ===")
for p in sorted(paths):
    print("  ", p)

print("\n=== x-codex-* 头 ===")
for h in sorted(headers):
    print("  ", h)

print("\n=== 额度字段相关字符串（前 50 条）===")
for s in sorted(jsonfields)[:50]:
    print("  ", s)
