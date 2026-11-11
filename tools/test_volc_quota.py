#!/usr/bin/env python3
"""用 zcode 里正在用的 ark key 实测火山额度接口。"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")


def live_keys():
    out = []
    p = os.path.join(HOME, ".zcode", "v2", "provider_config.json")
    if os.path.exists(p):
        raw = open(p, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"ark-[A-Za-z0-9\-_]{10,60}", raw):
            out.append((m.group(0), p))
    return out


def get(url, headers, label):
    print(f"\n--- {label} ---")
    print(f"    GET {url}")
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            print(f"    HTTP {r.status}: {body[:3000]}")
            return body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"    HTTP {e.code}: {body[:700]}")
    except Exception as e:  # noqa: BLE001
        print(f"    失败: {e}")
    return None


def main() -> int:
    keys = live_keys()
    if not keys:
        print("!! 没找到 live ark key")
        return 1
    key, src = keys[0]
    print(f"live ark key {key[:12]}... (len={len(key)}) 来自 {os.path.basename(src)}")

    hdr = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    host = "https://ark.cn-beijing.volces.com"
    for path in ("/api/plan", "/api/coding/plan", "/api/v3/plan", "/api/usage",
                 "/api/coding/v1/plan", "/api/coding/usage"):
        body = get(host + path, hdr, path)
        if body and '"error"' not in body:
            print("\n*** 命中可用接口:", path)
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
