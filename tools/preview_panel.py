#!/usr/bin/env python3
"""主面板截图（改版验收用）。

子进程渲染、PNG 走管道回父进程落盘（同 preview_configwin 的老办法：
渲染进程退出时 GDI 收尾会弄坏同进程写出的 PNG）。

    python tools/preview_panel.py
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))


def child(mode: str):
    from tokenboard.config import DB_PATH
    from tokenboard.scanner import Scanner
    from tokenboard.store import Store
    from tokenboard.ui.panel import Panel
    from wincap import capture_client

    store = Store(DB_PATH)
    panel = Panel(store, Scanner(store))
    panel.create()
    panel.resize_to = None
    if mode == "app":
        panel._view_idx = 0
        panel._expanded.add("minimax")
    elif mode == "model":
        panel._view_idx = 1
        panel._expanded.add("deepseek-v4.1-flash-1017")
    elif mode == "speed":
        panel._view_idx = 2
    elif mode == "quota":
        panel._view_idx = 3
        panel._quota = [
            {"provider": "minimax", "name": "MiniMax M Plan", "ok": True,
             "windows": [
                 {"kind": "5h", "used": 42, "remaining": 58, "reset_at": 0},
                 {"kind": "weekly", "used": 73, "remaining": 27, "reset_at": 0},
             ]},
            {"provider": "codex", "name": "Codex · Plus", "ok": True,
             "windows": [
                 {"kind": "5h", "used": 18, "remaining": 82,
                  "reset_at": (time.time() + 7200) * 1000},
                 {"kind": "weekly", "used": 61, "remaining": 39,
                  "reset_at": (time.time() + 3 * 86400) * 1000},
             ],
             "note": "剩余重置券 2 张"},
            {"provider": "volcengine", "name": "火山方舟编程包", "ok": False,
             "error": "未配置 AK/SK", "windows": [],
             "hint": "把 AccessKey 写到 ~/.tokenboard/volcengine.json"},
        ]
    panel._hover_row = 1
    panel.show()
    time.sleep(1.2)
    img = capture_client(panel.hwnd)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    sys.stdout.buffer.write(bio.getvalue())
    sys.stdout.buffer.flush()


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        child(sys.argv[2])
        return 0
    for mode in ("app", "model", "speed", "quota"):
        p = subprocess.run([sys.executable, os.path.abspath(__file__),
                            "--child", mode], capture_output=True)
        name = f"panel_{mode}.png"
        if p.returncode != 0:
            print(f"  {name} 子进程失败:",
                  p.stderr.decode("utf-8", "replace")[-900:])
            continue
        data = p.stdout
        path = os.path.join(ROOT, "tools", name)
        with open(path, "wb") as f:
            f.write(data)
        ok = data[:4] == b"\x89PNG"
        print(f"  {name:<20} {len(data):>7} 字节  PNG头={'OK' if ok else 'BAD'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())