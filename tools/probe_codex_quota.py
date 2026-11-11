#!/usr/bin/env python3
"""摸清本机 Codex 的安装位置、鉴权文件与额度接口线索。"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def show_tree(base, skip_dirs=("sessions", "log", "logs", "tmp"), max_depth=3):
    if not os.path.isdir(base):
        print(f"[不存在] {base}")
        return
    print(f"=== {base} ===")
    for root, dirs, files in os.walk(base):
        rel = os.path.relpath(root, base)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
                rel_f = os.path.join(rel, f) if rel != "." else f
                print(f"  {rel_f}  {st.st_size}  "
                      f"{time.strftime('%m-%d %H:%M', time.localtime(st.st_mtime))}")
            except Exception as e:
                print(f"  {f}  <err {e}>")


def find_codex_installs():
    bases = [
        os.path.expanduser("~/AppData/Roaming/npm/node_modules"),
        os.path.expanduser("~/.npm-global/lib/node_modules"),
        os.path.expanduser("~/.bun/install/global/node_modules"),
        os.path.expanduser("~/.local/share/pnpm/global/5/node_modules"),
        r"D:\software",
        r"C:\Program Files\nodejs",
    ]
    hits = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            depth = os.path.relpath(root, base).count(os.sep) + 1
            if depth > 4:
                dirs[:] = []
                continue
            low = root.lower()
            if os.sep + "codex" in low or low.endswith("codex"):
                if "package.json" in files:
                    hits.append(os.path.join(root, "package.json"))
                hits.append(root)
            if len(hits) > 40:
                return hits
    return hits


if __name__ == "__main__":
    show_tree(os.path.expanduser("~/.codex"))
    print()
    print("=== codex 安装候选 ===")
    for h in find_codex_installs():
        print("  ", h)
