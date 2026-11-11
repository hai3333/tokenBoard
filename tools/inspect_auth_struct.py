#!/usr/bin/env python3
"""看 MiniMax / Codex / Claude 本地配置的**结构**（不打印密钥值）。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")


def redact(obj, depth=0):
    if isinstance(obj, dict):
        return {k: redact(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, depth + 1) for v in obj[:8]]
    if isinstance(obj, str):
        low = obj.lower()
        if any(k in low for k in ("sk-", "apikey", "api_key", "token", "secret",
                                  "password", "bearer")):
            return f"<redacted len={len(obj)}>"
        if len(obj) > 70:
            return f"<str len={len(obj)}>"
        return obj
    return obj


def show(path, title, limit=2000):
    print("=" * 76)
    print(f"{title}: {path}")
    print("=" * 76)
    if not os.path.exists(path):
        print("  不存在")
        return
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except Exception as e:  # noqa: BLE001
        print("  读取失败", e)
        return
    try:
        data = json.loads(raw)
        print(json.dumps(redact(data), ensure_ascii=False, indent=1)[:limit])
    except Exception:  # noqa: BLE001
        # yaml 之类
        for line in raw.splitlines():
            if any(k in line.lower() for k in ("key", "token", "secret", "password")):
                k = line.split(":")[0]
                print(f"  {k}: <redacted>")
            else:
                print("  " + line[:160])
    print()


show(os.path.join(HOME, ".minimax", "config.yaml"), "MiniMax Code config")
show(os.path.join(HOME, ".minimax", "channel-routes.yaml"), "MiniMax channel routes")
show(os.path.join(HOME, ".minimax", "codex-auth.json"), "MiniMax codex-auth")
show(os.path.join(HOME, ".codex", "auth.json"), "Codex auth")
