#!/usr/bin/env python3
"""Sample each AI IDE's session log format to reverse-engineer token usage fields."""
import json
import os
import glob
from collections import Counter

HOME = os.path.expanduser("~")


def newest(pattern, limit=3):
    files = [f for f in glob.glob(pattern, recursive=True) if os.path.isfile(f)]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[:limit]


def show_jsonl(path, maxlines=400, label=""):
    print(f"\n{'='*70}\n### {label} :: {path}\n{'='*70}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[:maxlines]
    except Exception as e:  # noqa: BLE001
        print("  ERR", e)
        return
    keys = Counter()
    usage_blocks = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(o, dict):
            continue
        keys.update(o.keys())
        # hunt for usage anywhere
        def hunt(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "usage" and isinstance(v, dict):
                        usage_blocks.append((path + "/usage", v))
                    hunt(v, path + "/" + k)
            elif isinstance(node, list):
                for i, v in enumerate(node[:50]):
                    hunt(v, f"{path}[{i}]")
        hunt(o)
    print("  top-level keys:", dict(keys.most_common(15)))
    if usage_blocks:
        print("  usage block locations:", Counter(p for p, _ in usage_blocks).most_common(5))
        seen = set()
        for p, u in usage_blocks:
            k = tuple(sorted(u.keys()))
            if k in seen:
                continue
            seen.add(k)
            print(f"    @ {p} -> {u}")
    else:
        print("  NO 'usage' key found")


def show_json(path, label="", maxlen=1500):
    print(f"\n{'='*70}\n### {label} :: {path}\n{'='*70}")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception as e:  # noqa: BLE001
        print("  ERR", e)
        return
    print(txt[:maxlen])


if __name__ == "__main__":
    print("############ CLAUDE CODE ############")
    for p in newest(os.path.join(HOME, ".claude/projects/**/*.jsonl"), 2):
        show_jsonl(p, label="claude")

    print("\n\n############ CODEX ############")
    for p in newest(os.path.join(HOME, ".codex/sessions/**/*.jsonl"), 2):
        show_jsonl(p, label="codex")

    print("\n\n############ ZCODE dirs ############")
    for sub in ("projects", "session", "cli", "v2", "logs", "cache"):
        d = os.path.join(HOME, ".zcode", sub)
        if not os.path.isdir(d):
            continue
        print(f"\n--- .zcode/{sub} ---")
        try:
            for e in sorted(os.listdir(d))[:25]:
                full = os.path.join(d, e)
                if os.path.isdir(full):
                    inner = []
                    try:
                        inner = sorted(os.listdir(full))[:6]
                    except Exception:  # noqa: BLE001
                        pass
                    print(f"  [D] {e}  -> {inner}")
                else:
                    print(f"  [F] {e}  ({os.path.getsize(full)} bytes)")
        except Exception as e:  # noqa: BLE001
            print("  ERR", e)
