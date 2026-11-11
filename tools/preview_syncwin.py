#!/usr/bin/env python3
"""设置窗截图（外观 + WebDAV），暗色 / 亮色各一套。

沿用 preview_configwin 的老办法：子进程渲染、PNG 走管道回父进程落盘
（渲染进程退出时 GDI 收尾会弄坏同进程写出的 PNG）。

    python tools/preview_syncwin.py
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

LONG_PASS = "this-is-a-very-long-webdav-app-password-0123456789-abcdef"


def child(mode: str, theme: str = "dark"):
    from tokenboard.ui import theme as theme_mod
    theme_mod.apply(theme)

    from tokenboard.config import DB_PATH
    from tokenboard.store import Store
    from tokenboard.ui.syncwin import SyncWindow
    from wincap import capture_client

    store = Store(DB_PATH)
    win = SyncWindow(store, theme_pref="auto")
    win.create()
    win.show()
    time.sleep(0.9)

    if mode in ("filled", "longpass"):
        win.edits["url"].set_text("https://dav.jianguoyun.com/dav")
        win.edits["user"].set_text("me@example.com")
        win.edits["pass"].set_text("app-password" if mode == "filled" else LONG_PASS)
        win.edits["dir"].set_text("TokenBoard")
        win.edits["interval"].set_text("30")
        win._enabled = True
        win._set_status("连接正常 · 远端已有快照（12,345 条 / 2.3 MB）", "ok")
        win.invalidate()
    elif mode == "shown":
        win.edits["url"].set_text("https://dav.jianguoyun.com/dav")
        win.edits["user"].set_text("me@example.com")
        win.edits["pass"].set_text(LONG_PASS)
        win.edits["dir"].set_text("TokenBoard")
        win.edits["interval"].set_text("30")
        win._enabled = True
        win._apply_theme_pref("light")
        r = win._rects["btn_show"]
        win.on_click(r[0] + r[2] / 2, r[1] + r[3] / 2)
        win.invalidate()
    elif mode == "error":
        win.edits["url"].set_text("https://dav.example.com/dav")
        win._enabled = True
        win._set_status("认证失败（HTTP 401）：账号或密码不对，或者没有该目录的权限", "err")
        win.invalidate()
    time.sleep(0.6)

    img = capture_client(win.hwnd)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    sys.stdout.buffer.write(bio.getvalue())
    sys.stdout.buffer.flush()


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        child(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "dark")
        return 0
    for theme in ("dark", "light"):
        for mode in ("empty", "filled", "shown", "error"):
            p = subprocess.run([sys.executable, os.path.abspath(__file__),
                                "--child", mode, theme], capture_output=True)
            name = f"settings_{mode}_{theme}.png"
            if p.returncode != 0:
                print(f"  {name} 子进程失败:",
                      p.stderr.decode("utf-8", "replace")[-900:])
                continue
            data = p.stdout
            path = os.path.join(ROOT, "tools", name)
            with open(path, "wb") as f:
                f.write(data)
            ok = data[:4] == b"\x89PNG"
            print(f"  {name:<28} {len(data):>7} 字节  PNG头={'OK' if ok else 'BAD'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())