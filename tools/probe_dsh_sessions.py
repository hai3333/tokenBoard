#!/usr/bin/env python3
"""Decompress multi-frame zstd DSH sessions and map token usage structure."""
import sys
import os
import json
import glob
import zstandard
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.expanduser("~")
DSH = os.path.join(HOME, ".dsh")


def read_all(path):
    """Read every zstd frame (files are streamed = concatenated frames)."""
    dctx = zstandard.ZstdDecompressor()
    with open(path, "rb") as f:
        reader = dctx.stream_reader(f, read_across_frames=True)
        return reader.readall()


def find_usage(node, out, path=""):
    if isinstance(node, dict):
        keys = {k.lower() for k in node.keys()}
        if any(k in keys for k in ("input_tokens", "inputtokens", "prompt_tokens",
                                   "output_tokens", "outputtokens", "total_tokens",
                                   "totaltokens", "cache_read_input_tokens", "cached_tokens")):
            out.append((path, node))
        for k, v in node.items():
            find_usage(v, out, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            find_usage(v, out, f"{path}[{i}]")


def analyze(path, show_shape=True):
    print("\n" + "=" * 74)
    print(f"### {os.path.relpath(path, DSH)}  ({os.path.getsize(path)} B compressed)")
    print("=" * 74)
    try:
        raw = read_all(path)
    except Exception as e:  # noqa: BLE001
        print("  DECODE ERR:", e)
        return
    text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print(f"  decompressed {len(raw)} bytes -> {len(lines)} lines")

    topkeys = Counter()
    types = Counter()
    usage_hits = []
    for ln in lines:
        try:
            o = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(o, dict):
            continue
        topkeys.update(o.keys())
        if isinstance(o.get("type"), str):
            types[o["type"]] += 1
        hits = []
        find_usage(o, hits, "")
        for p, u in hits:
            usage_hits.append((p, u, o))
    print("  top-level keys:", dict(topkeys.most_common(14)))
    print("  type histogram:", dict(types.most_common(15)))
    print(f"  usage hits: {len(usage_hits)}")
    locs = Counter(p for p, _, _ in usage_hits)
    for l, c in locs.most_common(8):
        print(f"    {c:>5}x  {l}")
    if show_shape and usage_hits:
        seen = set()
        for p, u, o in usage_hits:
            k = tuple(sorted(u.keys()))
            if k in seen:
                continue
            seen.add(k)
            print(f"    SHAPE @ {p} -> {json.dumps(u, ensure_ascii=False)[:300]}")
            # show sibling context
            ctx = {kk: (json.dumps(vv, ensure_ascii=False)[:120] if not isinstance(vv, (int, float, str, type(None))) else vv)
                   for kk, vv in o.items()}
            print(f"    record: {json.dumps(ctx, ensure_ascii=False)[:600]}")
    return usage_hits


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(DSH, "sessions", "**", "*.zstd"), recursive=True),
                   key=os.path.getmtime, reverse=True)
    print(f"found {len(files)} dsh session files")
    for p in files[:3]:
        analyze(p)
