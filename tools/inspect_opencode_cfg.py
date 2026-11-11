#!/usr/bin/env python3
"""检查 opencode.jsonc 能否直接当 JSON 解析，以及 auth.json 的结构（脱敏）。"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

cfg_path = os.path.expandvars(r"%USERPROFILE%\.config\opencode\opencode.jsonc")
auth_path = os.path.expandvars(r"%USERPROFILE%\.local\share\opencode\auth.json")

raw = open(cfg_path, encoding="utf-8").read()
print(f"opencode.jsonc: {len(raw)} 字符")
print("  严格 JSON 解析:", end=" ")
try:
    obj = json.loads(raw)
    print("成功（可以当普通 JSON 处理）")
    print("  顶层键:", list(obj))
    print("  provider 列表:", list(obj.get("provider", {})))
    print("  当前 model:", obj.get("model"))
except Exception as e:  # noqa: BLE001
    print(f"失败 -> {e}")

# 有没有注释行
comment_lines = [i for i, ln in enumerate(raw.splitlines(), 1)
                 if ln.strip().startswith("//")]
print("  注释行:", comment_lines[:10], f"(共 {len(comment_lines)} 行)")
# 有没有尾逗号
import re
trailing = re.findall(r",\s*[\]}]", raw)
print("  可能的尾逗号:", len(trailing))

print(f"\nauth.json: {os.path.getsize(auth_path)} 字节")
try:
    auth = json.load(open(auth_path, encoding="utf-8"))
except Exception as e:  # noqa: BLE001
    print("  解析失败:", e)
    auth = None
if isinstance(auth, dict):
    for k, v in auth.items():
        if isinstance(v, dict):
            keys = list(v)
            print(f"  {k}: {keys}")
            for kk, vv in v.items():
                s = str(vv)
                print(f"      {kk}: {s[:12]}...{s[-6:]} ({len(s)}字符)")
        else:
            s = str(v)
            print(f"  {k}: {s[:20]}... ({len(s)}字符)")
