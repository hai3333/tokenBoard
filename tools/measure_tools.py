#!/usr/bin/env python3
"""对比各 AI 工具的真实内存占用（本机实测）。"""
import sys

import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def tree_rss(proc) -> tuple[float, float, int]:
    """返回 (自身 RSS, 含子进程合计 RSS, 子进程数)"""
    try:
        total = proc.memory_info().rss
        kids = proc.children(recursive=True)
        for k in kids:
            try:
                total += k.memory_info().rss
            except Exception:  # noqa: BLE001
                pass
        return proc.memory_info().rss / 1024 / 1024, total / 1024 / 1024, len(kids)
    except Exception:  # noqa: BLE001
        return -1, -1, 0


def find(names):
    out = []
    for p in psutil.process_iter(["name", "exe"]):
        try:
            nm = (p.info["name"] or "")
            if any(nm.lower() == n.lower() for n in names):
                out.append(p)
        except Exception:  # noqa: BLE001
            pass
    return out


TARGETS = [
    ("CC Switch", ["CC Switch.exe", "cc-switch.exe"]),
    ("DeepSeek Harness", ["DeepSeek Harness.exe"]),
    ("ZCode", ["ZCode.exe"]),
    ("MiniMax Code", ["MiniMax Code.exe"]),
    ("Codex", ["codex.exe"]),
    ("Cursor", ["Cursor.exe"]),
]

print("=" * 78)
print("本机正在运行的 AI 工具内存占用")
print("=" * 78)
print(f"{'进程':<22}{'自身 RSS':>12}{'含子进程':>12}{'子进程':>9}")
print("-" * 78)
grand = 0.0
for label, names in TARGETS:
    procs = find(names)
    if not procs:
        print(f"{label:<22}{'—':>12}{'—':>12}{'—':>9}")
        continue
    own, tot, n = 0.0, 0.0, 0
    for p in procs:
        o, t, c = tree_rss(p)
        own += o
        tot += t
        n += c
    grand += tot
    print(f"{label:<22}{own:>10.1f}MB{tot:>10.1f}MB{n:>9}")
print("-" * 78)
print(f"{'合计':<22}{'':>12}{grand:>10.1f}MB")
