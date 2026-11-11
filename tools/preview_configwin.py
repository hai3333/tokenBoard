#!/usr/bin/env python3
"""打开配置窗口并截图。

坑（勿改）：渲染进程退出时 GDI 收尾会把已经写好的 PNG 内容弄坏
（长度 +1024、内容被内存页覆盖），所以让**子进程渲染**，
PNG 字节走管道回传给父进程，由父进程落盘 —— 管道里的数据不受影响。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = r"D:\个人资料\项目\token看板"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))


def child(mode: str):
    """子进程：建窗口、渲染、把 PNG 字节写到 stdout。"""
    from tokenboard.config import DB_PATH
    from tokenboard.providers import ProviderStore
    from tokenboard.store import Store
    from tokenboard.ui.configwin import ConfigWindow
    from wincap import capture_client

    store = Store(DB_PATH)
    pstore = ProviderStore(store)
    if not pstore.list():
        n = pstore.import_from_opencode_config()
        print(f"[child] 从现有 opencode.jsonc 导入 {n} 个 provider", file=sys.stderr)

    win = ConfigWindow(pstore)
    win.create()
    win.show()
    time.sleep(1.0)
    win.reload()
    time.sleep(0.6)

    if mode == "dd":
        r = win._rects["f_default"]
        win.on_click(r[0] + r[2] / 2, r[1] + r[3] / 2)
        time.sleep(0.5)
    elif mode == "key":
        r = win._rects["btn_show"]
        win.on_click(r[0] + r[2] / 2, r[1] + r[3] / 2)
        time.sleep(0.5)

    img = capture_client(win.hwnd)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    sys.stdout.buffer.write(bio.getvalue())
    sys.stdout.buffer.flush()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2])
        return 0

    from PIL import Image
    for mode, name in (("main", "config_window.png"),
                       ("dd", "config_window_dd.png"),
                       ("key", "config_window_key.png")):
        p = subprocess.run([sys.executable, os.path.abspath(__file__),
                            "--child", mode], capture_output=True)
        if p.returncode != 0:
            print(f"  {name} 子进程失败:",
                  p.stderr.decode("utf-8", "replace")[-600:])
            continue
        data = p.stdout
        path = os.path.join(ROOT, "tools", name)
        with open(path, "wb") as f:
            f.write(data)
        ok = data[:4] == b"\x89PNG"
        try:
            im = Image.open(path)
            size = im.size
        except Exception as e:  # noqa: BLE001
            size = f"损坏: {e}"
        print(f"  {name:<24} {len(data):>7} 字节  PNG头={'OK' if ok else 'BAD'}  {size}")


if __name__ == "__main__":
    main()
