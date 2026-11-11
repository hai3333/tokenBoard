#!/usr/bin/env python3
"""Extract strings from dsh-desktop LevelDB + inventory other AI IDE data dirs."""
import sys
import os
import re
import glob

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")
DS = os.path.join(HOME, "AppData/Roaming/@deepseek-ai/dsh-desktop")


def strings(path, minlen=6):
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except Exception as e:  # noqa: BLE001
        print("  ERR", path, e)
        return
    print(f"\n--- {path} ({len(blob)} bytes) ---")
    for m in re.finditer(rb"[\x20-\x7e\xc0-\xff][\x20-\x7e]{%d,}" % minlen, blob):
        s = m.group().decode("utf-8", errors="replace")
        print("   ", s[:300])


print("=" * 70)
print("dsh-desktop Local Storage / Session Storage strings")
print("=" * 70)
for p in glob.glob(os.path.join(DS, "**", "*.log"), recursive=True):
    if "leveldb" in p.lower() or "session storage" in p.lower():
        strings(p)

print("\n" + "=" * 70)
print("Other AI IDE data dirs inventory")
print("=" * 70)
cands = {
    "gemini": os.path.join(HOME, ".gemini"),
    "opencode": os.path.join(HOME, ".local/share/opencode"),
    "opencode2": os.path.join(HOME, ".config/opencode"),
    "cursor": os.path.join(HOME, ".cursor"),
    "trae": os.path.join(HOME, ".trae"),
    "cline": os.path.join(HOME, ".cline"),
    "codebuddy": os.path.join(HOME, ".codebuddy"),
    "minimax": os.path.join(HOME, ".minimax"),
}
for name, d in cands.items():
    if not os.path.isdir(d):
        print(f"\n### {name}: NOT FOUND ({d})")
        continue
    print(f"\n### {name}: {d}")
    try:
        entries = sorted(os.listdir(d))[:20]
    except Exception as e:  # noqa: BLE001
        print("   ERR", e)
        continue
    for e in entries:
        full = os.path.join(d, e)
        if os.path.isdir(full):
            inner = []
            try:
                inner = sorted(os.listdir(full))[:8]
            except Exception:  # noqa: BLE001
                pass
            print(f"   [D] {e} -> {inner}")
        else:
            print(f"   [F] {e} ({os.path.getsize(full)})")
