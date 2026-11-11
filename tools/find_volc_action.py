#!/usr/bin/env python3
"""挖 cc-switch.exe 里火山 Ark 用量查询的确切 Action / 路径。"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
exe = r"D:\software\CC-Switch-v3.9.0-3-Windows-Portable\css15\cc-switch.exe"
b = open(exe, "rb").read()

# 把 exe 里的字符串序列抽出来（Rust 编译产物里是连续的 ASCII/UTF-8 字面量）
print("=" * 78)
print("### 含 volcengine / ark / usage 的长字符串")
print("=" * 78)
strs = re.findall(b"[\x20-\x7e\xe4-\xe9]{12,400}", b)
seen = set()
for s in strs:
    t = s.decode("utf-8", "replace")
    low = t.lower()
    if "volcengine" in low or "open.volcengineapi" in low:
        if t in seen:
            continue
        seen.add(t)
        print(f"  {t[:390]}")
print()

print("=" * 78)
print("### 可能的上游 Action 名（Query*/Describe*）")
print("=" * 78)
cands = set()
for s in strs:
    t = s.decode("utf-8", "replace")
    for m in re.finditer(r"(Query|Describe|Get|List)[A-Za-z]{3,40}(Usage|Quota|Limit|Plan|Billing|Resource)",
                         t):
        cands.add(m.group(0))
for c in sorted(cands):
    print("  ", c)

print()
print("=" * 78)
print("### 含 'ark' 的路径样式字符串")
print("=" * 78)
paths = set()
for s in strs:
    t = s.decode("utf-8", "replace")
    for m in re.finditer(r"/[a-zA-Z0-9_./\-]*(?:usage|quota|limit|plan|billing)[a-zA-Z0-9_./\-]*",
                         t):
        p = m.group(0)
        if len(p) > 5 and not p.startswith("/api/v1/chat"):
            paths.add(p)
for p in sorted(paths)[:60]:
    print("  ", p)
