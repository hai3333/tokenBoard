#!/usr/bin/env python3
"""面板预览：隔离抓取自绘窗口（DWM 路径），写 PNG 到 tools/。

路线同 tools/preview_configwin.py：
    python tools/preview_panel.py            # 三张：默认 / 搜索态 / 右键菜单
子进程 --child <mode> 负责建窗+抓图，PNG 字节走 stdout，
本进程只负责落盘（避免加密文件系统把「创建了窗口的进程」写的图打花）。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ROOT) if os.path.basename(ROOT) == "tools" else ROOT
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))


def child(mode: str):
    from tokenboard.config import DB_PATH
    from tokenboard.pricing import get_pricing
    from tokenboard.scanner import Scanner
    from tokenboard.store import Store
    from tokenboard.ui.panel import Panel
    from wincap import capture_client

    store = Store(DB_PATH)
    store.load_pricing(get_pricing().pricing_map())
    scanner = Scanner(store)
    p = Panel(store, scanner)
    p.create()
    p.show()
    time.sleep(1.5)

    if mode == "search":
        p._search_focus = True
        for ch in "claude":
            p.on_char(ch)
        p._load()
    elif mode == "ctx":
        i = next(i for i, r in enumerate(p._rows)
                 if r["kind"] not in ("sub", "ssub"))
        rx, ry, rw, rh = p._row_rect(i)
        p.on_right_click(rx + 30, ry + rh / 2)
    elif mode == "footer":
        pass

    from tokenboard.ui.win32 import MSG, user32
    msg = MSG()
    end = time.time() + 0.6
    while time.time() < end:
        while user32.PeekMessageW(__import__("ctypes").byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(__import__("ctypes").byref(msg))
            user32.DispatchMessageW(__import__("ctypes").byref(msg))
        time.sleep(0.02)

    img = capture_client(p.hwnd)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    sys.stdout.buffer.write(bio.getvalue())
    sys.stdout.buffer.flush()


def main() -> int:
    modes = sys.argv[1:] if len(sys.argv) > 1 else ["default", "search", "ctx"]
    for mode in modes:
        out = subprocess.run(
            [sys.executable, __file__, "--child", mode],
            capture_output=True,
            timeout=60,
        )
        if out.returncode != 0 or not out.stdout:
            print(f"[{mode}] child failed: rc={out.returncode}", file=sys.stderr)
            if out.stderr:
                print(out.stderr.decode("utf-8", "replace"), file=sys.stderr)
            continue
        out_path = os.path.join(ROOT, "tools", f"panel_preview_{mode}.png")
        with open(out_path, "wb") as f:
            f.write(out.stdout)
        print(f"saved {out_path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2])
    else:
        sys.exit(main())
