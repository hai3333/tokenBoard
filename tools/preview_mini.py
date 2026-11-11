#!/usr/bin/env python3
"""mini 悬停预览：隔离子进程抓 DWM，PNG 字节走 stdout（长度前缀帧）。

    python tools/preview_mini.py
"""
from __future__ import annotations

import io
import os
import struct
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))


def child():
    from tokenboard.config import DB_PATH
    from tokenboard.pricing import get_pricing
    from tokenboard.store import Store
    from tokenboard.ui.mini import MiniBar
    from tokenboard.ui.win32 import MSG, user32
    from wincap import capture_client
    import ctypes

    store = Store(DB_PATH)
    store.load_pricing(get_pricing().pricing_map())

    def pump(ms: int) -> None:
        msg = MSG()
        end = time.time() + ms / 1000
        while time.time() < end:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)

    frames: list[tuple[str, bytes]] = []
    for hover in (False, True):
        win = MiniBar(store, lambda: None)
        win.create()
        win.show()
        win._load()
        win._hover = hover
        win.invalidate()
        pump(600)
        img = capture_client(win.hwnd)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        frames.append(("hover" if hover else "normal", bio.getvalue()))
        win.destroy()
        pump(100)

    out = sys.stdout.buffer
    for name, data in frames:
        out.write(name.encode("ascii") + b"\n" + struct.pack("<I", len(data)) + data)
    out.flush()
    os._exit(0)          # 硬退出，跳过一切可能卡住的清理


def main() -> int:
    proc = subprocess.Popen([sys.executable, __file__, "--child"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        raw, err = proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("child timeout", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        print(err.decode("utf-8", "replace"), file=sys.stderr)
        return 1
    i = 0
    while i < len(raw):
        j = raw.find(b"\n", i)
        name = raw[i:j].decode("ascii")
        (size,) = struct.unpack_from("<I", raw, j + 1)
        data = raw[j + 5: j + 5 + size]
        path = os.path.join(ROOT, "tools", f"mini_preview_{name}.png")
        with open(path, "wb") as f:
            f.write(data)
        print(f"saved {path} ({size} bytes)")
        i = j + 5 + size
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child()
    else:
        sys.exit(main())
