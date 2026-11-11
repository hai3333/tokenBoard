#!/usr/bin/env python3
"""打包：生成免安装 ZIP + 单文件安装器。"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = "1.0.0"


def zip_portable() -> Path:
    src = DIST / "TokenBoard"
    out = DIST / f"TokenBoard-{VERSION}-portable.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in src.rglob("*"):
            if p.is_file():
                z.write(p, Path("TokenBoard") / p.relative_to(src))
    return out


def main() -> int:
    files = [
        DIST / "TokenBoard-Setup-1.0.0.exe",
        DIST / "TokenBoard-Setup" / "TokenBoard-Setup.exe",
    ]
    print("=== 产物 ===")
    for f in files:
        if f.exists():
            print(f"  {f.name:<34} {f.stat().st_size / 1048576:>7.2f} MB")
    zp = zip_portable()
    print(f"  {zp.name:<34} {zp.stat().st_size / 1048576:>7.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
