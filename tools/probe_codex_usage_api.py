#!/usr/bin/env python3
"""实测 Codex(ChatGPT) 额度端点。"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AUTH = os.path.join(os.path.expanduser("~/.codex"), "auth.json")
with open(AUTH, encoding="utf-8") as f:
    auth = json.load(f)

tok = auth["tokens"]
access = tok["access_token"]
account = tok.get("account_id", "")

BASE = "https://chatgpt.com/backend-api"

HEADERS = {
    "Authorization": f"Bearer {access}",
    "ChatGPT-Account-Id": account,
    "Content-Type": "application/json",
    "User-Agent": "codex_cli_rs/0.0.0",
    "Accept": "application/json",
    "OpenAI-Beta": "codex",
}

CANDIDATES = [
    ("GET", f"{BASE}/wham/usage", None),
    ("GET", f"{BASE}/wham/profiles/me", None),
    ("GET", f"{BASE}/codex/usage", None),
    ("GET", f"{BASE}/wham/rate-limit-reset-credits", None),
    ("GET", f"{BASE}/wham/usage/thread_usage/query", None),
    ("GET", f"{BASE}/wham/usage/thread-estimates/query", None),
    ("GET", f"{BASE}/wham/settings/user", None),
]


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


for method, url, body in CANDIDATES:
    status, raw = call(method, url, body)
    print(f"\n{'=' * 70}\n{method} {url}\n-> HTTP {status}")
    if status == 200:
        try:
            print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2)[:3000])
        except Exception:
            print(raw[:1500])
    else:
        print(raw[:800])
