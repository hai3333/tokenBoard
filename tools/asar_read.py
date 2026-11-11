#!/usr/bin/env python3
"""极简 asar 读取器：按文件表里的 offset/size 把文件抠出来。"""
import json
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def read_asar(path):
    with open(path, "rb") as f:
        data = f.read()
    # 头部：4 字节 pickle size + 4 字节 header size + 4 字节 str size + JSON
    hdr_size = struct.unpack("<I", data[12:16])[0]
    header = json.loads(data[16:16 + hdr_size].decode("utf-8"))
    base = 16 + hdr_size
    return header, data, base


def find_files(node, prefix=""):
    out = []
    files = node.get("files", {})
    for name, info in files.items():
        p = f"{prefix}{name}"
        if "files" in info:
            out.extend(find_files(info, p + "/"))
        else:
            out.append((p, info))
    return out


def extract(path, want):
    header, data, base = read_asar(path)
    for p, info in find_files(header):
        if p == want or p.endswith("/" + want):
            off = int(info.get("offset", 0))
            size = int(info.get("size", 0))
            return data[base + off: base + off + size]
    return None


if __name__ == "__main__":
    ASAR = r"D:\software\minimaxcode\MiniMax Code\resources\app.asar"
    header, data, base = read_asar(ASAR)
    files = find_files(header)
    print(f"asar 内共 {len(files)} 个文件")
    print("\n=== 含 quota / usage / coding / subscription 的文件 ===")
    for p, info in files:
        low = p.lower()
        if any(k in low for k in ("quota", "usage", "coding", "subscription",
                                  "remains", "plan")):
            print(f"   {p}  ({info.get('size')} bytes)")

    print("\n=== 找 usage-script / coding plan 相关 ===")
    for p, info in files:
        if "openplatform" in p.lower() or "platform" in p.lower():
            print(f"   {p}  ({info.get('size')})")

    for want in ("subscription-quota.js",):
        blob = extract(ASAR, want)
        if blob:
            print(f"\n=== {want} ===")
            print(blob.decode("utf-8", "replace")[:6000])
