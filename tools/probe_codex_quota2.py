#!/usr/bin/env python3
"""查 Codex 额度数据的存放位置：
1. state_5.sqlite 里有没有 rate limit 表
2. .codex-global-state.json 里有没有额度字段
3. auth.json 的结构（只看键名，不打印密钥）
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CODEX = os.path.expanduser("~/.codex")


def dump_auth():
    p = os.path.join(CODEX, "auth.json")
    print("=== auth.json 结构 ===")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)

    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                p2 = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (dict, list)):
                    walk(v, p2)
                else:
                    s = str(v)
                    if len(s) > 24 or any(t in k.lower() for t in
                                         ("token", "key", "secret", "password")):
                        s = s[:20] + f"...<len={len(str(v))}>"
                    print(f"  {p2} = {s} (type={type(v).__name__})")
        elif isinstance(obj, list):
            print(f"  {prefix} = [list len={len(obj)}]")

    walk(d)


def dump_state_db():
    p = os.path.join(CODEX, "state_5.sqlite")
    print("\n=== state_5.sqlite 表 ===")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    for (name, sql) in con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"):
        print(f"  [{name}]")
        if sql and any(t in sql.lower() for t in
                       ("rate", "limit", "usage", "quota", "credit")):
            print(f"      {sql[:400]}")
    con.close()


def dump_global_state():
    p = os.path.join(CODEX, ".codex-global-state.json")
    print("\n=== .codex-global-state.json 顶层键 + 额度相关 ===")
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    for k in list(d.keys()):
        v = d[k]
        n = len(v) if isinstance(v, (dict, list, str)) else 1
        print(f"  {k}  ({type(v).__name__}, len={n})")

    print("\n  --- 递归搜 rate/limit/usage/quota/credit 关键字 ---")
    hits = []

    def walk(obj, path="", depth=0):
        if depth > 6:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                p2 = f"{path}.{k}" if path else k
                if any(t in k.lower() for t in
                       ("rate", "limit", "usage", "quota", "credit", "weekly")):
                    hits.append((p2, str(v)[:200]))
                walk(v, p2, depth + 1)
        elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
            for i, it in enumerate(obj[:3]):
                walk(it, f"{path}[{i}]", depth + 1)

    walk(d)
    for p2, v in hits[:40]:
        print(f"  {p2} = {v}")
    if not hits:
        print("  (无命中)")


if __name__ == "__main__":
    dump_auth()
    dump_state_db()
    dump_global_state()
