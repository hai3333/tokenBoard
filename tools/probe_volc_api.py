#!/usr/bin/env python3
"""探火山 OpenAPI 网关，找 GetCodingPlanUsage 的正确用法。"""
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "https://open.volcengineapi.com/"


def probe(url, label):
    print(f"\n--- {label} ---")
    print(f"    {url}")
    req = urllib.request.Request(url, headers={"Accept": "application/json"},
                                 method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"    HTTP {r.status}: {r.read().decode('utf-8', 'replace')[:900]}")
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:900]}")
    except Exception as e:  # noqa: BLE001
        print(f"    失败: {e}")


for ver in ("2024-01-01", "2023-06-01", "2022-12-12", "2024-05-01", "2025-01-01"):
    probe(f"{HOST}?Action=GetCodingPlanUsage&Version={ver}", f"Action=GetCodingPlanUsage V={ver}")

probe(f"{HOST}?Action=GetCodingPlanUsage", "不带 Version")
probe("https://open.volcengineapi.com/?Action=ListActions", "列 Action")
