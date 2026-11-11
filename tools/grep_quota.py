#!/usr/bin/env python3
"""在应用包里定位「订阅额度」接口（带上下文）。"""
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATTERNS = [
    rb"coding[_-]?plan", rb"code[_-]?plan", rb"subscription", rb"quota",
    rb"usage[_-]?info", rb"remain[a-z_]*", rb"reset[_-]?(time|at|after)",
    rb"plan[_-]?info", rb"5[_-]?hour", rb"weekly[_-]?limit",
]


def grep_ctx(path, label, pats, ctx=260, limit=40):
    print("=" * 78)
    print(f"{label}: {path}")
    print("=" * 78)
    if not os.path.exists(path):
        print("  不存在")
        return
    data = open(path, "rb").read()
    shown = 0
    seen = set()
    for pat in pats:
        for m in re.finditer(pat, data, re.I):
            s = max(0, m.start() - ctx)
            frag = data[s:m.start() + ctx]
            text = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]", b" ", frag)
            text = re.sub(rb" +", b" ", text)
            key = text[:80]
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{pat.decode()}] ...{text.decode('utf-8', 'replace')}...")
            shown += 1
            if shown >= limit:
                print("  (达到上限)")
                return
            break  # 每个 pattern 只看第一处，避免刷屏
    if not shown:
        print("  (无匹配)")


if __name__ == "__main__":
    targets = []
    for pat in (r"C:\Program Files*\**\cc-switch.exe",
                r"C:\Program Files*\**\CC Switch.exe",
                os.path.expanduser(r"~\AppData\Local\**\cc-switch.exe"),
                os.path.expanduser(r"~\AppData\Local\**\CC Switch.exe")):
        targets += glob.glob(pat, recursive=True)
    for p in targets[:3]:
        grep_ctx(p, "CC Switch", PATTERNS)

    asar = r"D:\software\minimaxcode\MiniMax Code\resources\app.asar"
    grep_ctx(asar, "MiniMax Code asar", PATTERNS, limit=40)
