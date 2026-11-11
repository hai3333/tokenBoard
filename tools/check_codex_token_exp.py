#!/usr/bin/env python3
"""看 Codex access_token 的有效期，判断要不要做自动刷新。"""
import base64
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

auth = json.loads(open(os.path.expanduser("~/.codex/auth.json"), encoding="utf-8").read())
tok = auth["tokens"]["access_token"]

parts = tok.split(".")
if len(parts) >= 2:
    pad = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(pad))
    now = time.time()
    exp = payload.get("exp", 0)
    print("JWT payload:")
    for k, v in payload.items():
        if k in ("exp", "iat"):
            continue
        s = str(v)
        print(f"  {k} = {s[:120]}")
    print(f"  iat = {payload.get('iat')} ({time.strftime('%Y-%m-%d %H:%M', time.localtime(payload.get('iat', 0)))})")
    print(f"  exp = {exp} ({time.strftime('%Y-%m-%d %H:%M', time.localtime(exp))})")
    print(f"  剩余有效 = {(exp - now) / 3600:.1f} 小时")
print("last_refresh =", auth.get("last_refresh"))
