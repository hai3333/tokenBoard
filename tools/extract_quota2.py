#!/usr/bin/env python3
"""1) 抠 MiniMax 额度投影函数与 origin；2) 找 cc-switch.exe 真实路径。"""
import os
import re
import subprocess
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from tools.asar_read import read_asar, find_files  # noqa: E402

ASAR = r"D:\software\minimaxcode\MiniMax Code\resources\app.asar"
header, data, base = read_asar(ASAR)
files = find_files(header)

# 1) 完整的额度投影函数
for p, info in files:
    if not p.endswith(".js"):
        continue
    off, size = int(info.get("offset", 0)), int(info.get("size", 0))
    if size == 0 or size > 2_000_000:
        continue
    txt = data[base + off: base + off + size].decode("utf-8", "replace")
    if "current_interval_remaining_percent" in txt and "quotaType" in txt:
        i = txt.find("current_interval_remaining_percent")
        # 往回找函数头
        start = max(0, txt.rfind("function", 0, i) - 40)
        print("=" * 78)
        print(f"### 额度投影函数  ({p})")
        print("=" * 78)
        print(txt[start:start + 2200])
        break

# 2) OPEN_PLATFORM_ORIGINS
print("\n" + "=" * 78)
print("### OPEN_PLATFORM_ORIGINS")
print("=" * 78)
for p, info in files:
    if not p.endswith(".js"):
        continue
    off, size = int(info.get("offset", 0)), int(info.get("size", 0))
    if size == 0 or size > 2_000_000:
        continue
    txt = data[base + off: base + off + size].decode("utf-8", "replace")
    m = re.search(r"OPEN_PLATFORM_ORIGINS\s*=\s*\{", txt)
    if m:
        print(f"({p})")
        print(txt[m.start():m.start() + 700])
        break

# 3) cc-switch.exe 真实路径
print("\n" + "=" * 78)
print("### cc-switch 路径")
print("=" * 78)
for lnk in (r"C:\Users\17398\Desktop\CC Switch.lnk",
            r"C:\Users\17398\Desktop\cc-switch.exe (2).lnk",
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\CC Switch\CC Switch.lnk"):
    if not os.path.exists(lnk):
        continue
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
          f"$s.TargetPath")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True)
    print(f"  {os.path.basename(lnk)} -> {r.stdout.strip()}")

# 4) MiniMax 本地 auth
print("\n" + "=" * 78)
print("### ~/.minimax 里的 auth 存储")
print("=" * 78)
for root, dirs, fnames in os.walk(os.path.expanduser(r"~\.minimax\auth")):
    for f in fnames:
        p = os.path.join(root, f)
        print(f"  {p} ({os.path.getsize(p)})")
        if f.endswith((".json", ".yaml", ".yml", ".db")):
            raw = open(p, encoding="utf-8", errors="replace").read()
            red = re.sub(r'(["\']?(?:access_?token|token|api_?key|secret|password)'
                          r'["\']?\s*[:=]\s*)["\'][^"\']{8,}["\']',
                          r'\1"<redacted>"', raw, flags=re.I)
            print("     ", red[:500].replace("\n", "\n      "))
