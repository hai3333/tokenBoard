#!/usr/bin/env python3
"""模型汇总自检。"""
import sys
import os

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tokenboard.config import DB_PATH
from tokenboard.store import Store

s = Store(DB_PATH)
ms = s.models_aggregated()
print(f"归一后模型数: {len(ms)}")
print(f"{'模型':<36}{'tokens':>12}{'请求':>8}  {'主应用':<10}别名")
for m in ms:
    print(f"  {m['name']:<34} {m['total_tokens'] / 1e6:>9.1f}M {m['requests']:>7}  "
          f"{m['app']:<10}{len(m['aliases'])}")
    if len(m["aliases"]) > 1:
        print(f"      合并自: {', '.join(m['aliases'])}")
