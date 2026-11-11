#!/usr/bin/env python3
"""抓火山 Ark plan 接口的完整上下文（URL / 方法 / 鉴权 / 字段）。"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
exe = r"D:\software\CC-Switch-v3.9.0-3-Windows-Portable\css15\cc-switch.exe"
b = open(exe, "rb").read()

strs = re.findall(b"[\x20-\x7e\xe4-\xe9]{8,600}", b)
joined = [s.decode("utf-8", "replace") for s in strs]

KEYS = ["volces.com/api/plan", "AFPFiveHour", "five_hour", "AFPWeekly",
        "QuotaUsed", "ResetTime", "ark.cn-beijing", "GetCodingPlanUsage",
        "QueryInterval", "model_remains", "accessKeyId", "secretAccessKey"]

for key in KEYS:
    print("=" * 78)
    print(f"### {key}")
    print("=" * 78)
    n = 0
    for t in joined:
        i = t.find(key)
        if i < 0:
            continue
        s = max(0, i - 700)
        print(f"  ...{t[s:i + 700]}...")
        print()
        n += 1
        if n >= 2:
            break
    if not n:
        print("  (无)")
