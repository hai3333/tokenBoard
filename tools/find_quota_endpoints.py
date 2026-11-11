#!/usr/bin/env python3
"""从 CC Switch / MiniMax Code 的安装包里找「订阅额度」查询接口。"""
import os
import re
import sys
import glob

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{6,120}")
KEYWORDS = (b"quota", b"usage", b"limit", b"subscription", b"coding_plan",
            b"codingPlan", b"volcengine", b"minimax", b"remain", b"reset")


def scan(path, label, max_hits=60):
    print("=" * 76)
    print(f"{label}\n  {path}")
    print("=" * 76)
    if not os.path.exists(path):
        print("  不存在")
        return
    try:
        data = open(path, "rb").read()
    except Exception as e:  # noqa: BLE001
        print("  读取失败:", e)
        return
    urls = set()
    for m in URL_RE.finditer(data):
        u = m.group().decode("utf-8", "replace")
        low = u.lower()
        if any(k.decode() in low for k in KEYWORDS):
            urls.add(u)
    for u in sorted(urls)[:max_hits]:
        print("   ", u)
    if not urls:
        print("   (没匹配到额度相关 URL)")


def find_cc_switch():
    cands = []
    for pat in (r"C:\Program Files*\**\cc-switch.exe",
                r"C:\Program Files*\**\CC Switch.exe",
                os.path.expanduser(r"~\AppData\Local\**\cc-switch.exe"),
                os.path.expanduser(r"~\AppData\Local\**\CC Switch.exe")):
        cands += glob.glob(pat, recursive=True)
    return cands[:5]


if __name__ == "__main__":
    for p in find_cc_switch():
        scan(p, "CC Switch 可执行文件")
    for p in glob.glob(r"D:\software\minimaxcode\MiniMax Code\resources\*.asar"):
        scan(p, "MiniMax Code 资源包")
    for p in glob.glob(r"D:\software\minimaxcode\MiniMax Code\resources\app\**\*.js",
                       recursive=True):
        scan(p, "MiniMax Code JS")
