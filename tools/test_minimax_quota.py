#!/usr/bin/env python3
"""实测 MiniMax 额度接口（不打印 token）。"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")


def find_token():
    """取**未过期**的最新一条 accessToken（auth.json 里可能有多条历史记录）。"""
    import time
    base = os.path.join(HOME, ".minimax", "auth")
    now = time.time() * 1000
    best = None
    for root, dirs, files in os.walk(base):
        if "auth.json" not in files:
            continue
        p = os.path.join(root, "auth.json")
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for rec in (data.get("records") or {}).values():
            tok = rec.get("accessToken")
            exp = rec.get("expiresAtMs") or 0
            if tok and exp > now and (best is None or exp > best[1]):
                best = (tok, exp, p)
    if not best:
        return None, None, None
    tok, exp, p = best
    state = os.path.join(os.path.dirname(p), "auth-state.json")
    st = {}
    if os.path.exists(state):
        st = json.load(open(state, encoding="utf-8"))
    return tok, st.get("region", "cn"), st.get("buildEnv", "prod")


ORIGINS = {
    ("cn", "prod"): "https://www.minimaxi.com",
    ("en", "prod"): "https://platform.minimax.io",
}


def main() -> int:
    tok, region, env = find_token()
    if not tok:
        print("!! 找不到 accessToken")
        return 1
    print(f"token 长度 {len(tok)}  region={region}  buildEnv={env}")
    origin = ORIGINS.get((region, env), "https://www.minimaxi.com")
    url = f"{origin}/v1/api/openplatform/coding_plan/remains"
    print(f"GET {url}")

    for extra in ({}, {"X-Group-Id": ""}):
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {tok}",
            "User-Agent": "MiniMaxCode/1.0",
        }
        headers.update(extra)
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read().decode("utf-8", "replace")
                print(f"\n--- HTTP {r.status} (带 {list(extra)} 头) ---")
                print(body[:3000])
        except urllib.error.HTTPError as e:
            print(f"\n--- HTTP {e.code} ---")
            print(e.read().decode("utf-8", "replace")[:800])
        except Exception as e:  # noqa: BLE001
            print(f"\n--- 请求失败: {e} ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
