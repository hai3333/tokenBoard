#!/usr/bin/env python3
"""Find exact usage payload shapes for zcode, and hunt deepseek dsh-desktop token storage."""
import json
import os
import glob
import sqlite3
from collections import Counter

HOME = os.path.expanduser("~")


def deep_find_usage(obj, out, path=""):
    """Recursively find dicts whose keys look like token counters."""
    if isinstance(obj, dict):
        keys = {k.lower() for k in obj.keys()}
        if any(k in keys for k in ("input_tokens", "inputtokens", "prompt_tokens", "prompttokens",
                                   "output_tokens", "outputtokens", "completion_tokens",
                                   "total_tokens", "totaltokens", "cachereadinputtokens",
                                   "cache_read_input_tokens")):
            out.append((path, obj))
        for k, v in obj.items():
            deep_find_usage(v, out, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            deep_find_usage(v, out, f"{path}[{i}]")


print("=" * 70)
print("ZCODE model-io : response sub-structure")
print("=" * 70)
for p in sorted(glob.glob(os.path.join(HOME, ".zcode/cli/rollout/*.jsonl")),
                key=os.path.getmtime, reverse=True)[:3]:
    print(f"\n-- {os.path.basename(p)}")
    with open(p, encoding="utf-8", errors="replace") as f:
        for i, ln in enumerate(f):
            if i >= 40:
                break
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            resp = o.get("response")
            print(f"  top keys: {sorted(o.keys())}")
            print(f"  response type={type(resp).__name__} keys={sorted(resp.keys()) if isinstance(resp,dict) else ''}")
            if isinstance(resp, dict):
                for k, v in resp.items():
                    if k in ("body", "content", "text"):
                        sv = json.dumps(v, ensure_ascii=False)
                        print(f"    response.{k}: {sv[:200]}")
                    else:
                        print(f"    response.{k}: {json.dumps(v, ensure_ascii=False)[:300]}")
            found = []
            deep_find_usage(o, found, "")
            for path, u in found[:4]:
                print(f"    USAGE @ {path} -> {json.dumps(u, ensure_ascii=False)[:400]}")
            break

print("\n" + "=" * 70)
print("ZCODE cli/log jsonl")
print("=" * 70)
for p in sorted(glob.glob(os.path.join(HOME, ".zcode/cli/log/*.jsonl")),
                key=os.path.getmtime, reverse=True)[:1]:
    print(f"-- {p}")
    with open(p, encoding="utf-8", errors="replace") as f:
        for i, ln in enumerate(f):
            if i >= 30:
                break
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            s = json.dumps(o, ensure_ascii=False)
            if "token" in s.lower() or "usage" in s.lower():
                print("   ", s[:600])

print("\n" + "=" * 70)
print("ZCODE db message/part : any token fields?")
print("=" * 70)
db = os.path.join(HOME, ".zcode/cli/db/db.sqlite")
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
for t in ("message", "part", "session_entry"):
    n = conn.execute(
        "select count(*) from (select data from %s where lower(data) like '%%token%%' "
        "or lower(data) like '%%usage%%')" % t).fetchone()[0]
    print(f"  {t}: {n} rows mentioning token/usage")
    for r in conn.execute(
            "select data from %s where lower(data) like '%%token%%' limit 3" % t):
        print("     ", r["data"][:500])

print("\n" + "=" * 70)
print("DEEPSEEK dsh-desktop : hunt for token data")
print("=" * 70)
ds = os.path.join(HOME, "AppData/Roaming/@deepseek-ai/dsh-desktop")
for root, dirs, files in os.walk(ds):
    dirs[:] = [d for d in dirs if d not in ("Cache", "Code Cache", "GPUCache", "DawnGraphiteCache",
                                            "DawnWebGPUCache", "GrShaderCache", "ShaderCache",
                                            "GPUPersistentCache", "Code Cache", "blob_storage")]
    for f in files:
        p = os.path.join(root, f)
        rel = os.path.relpath(p, ds)
        try:
            sz = os.path.getsize(p)
        except Exception:  # noqa: BLE001
            continue
        print(f"  {rel}  ({sz})")
