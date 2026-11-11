#!/usr/bin/env python3
"""同步界面链路验收：真开窗、真跑一次同步、检查状态文字。

不依赖鼠标点击，直接调窗口/面板的方法再手动泵消息，
覆盖「后台线程 -> 队列 -> on_timer -> 界面状态」这条最容易出错的链路。

    python tools/test_sync_ui.py
"""
from __future__ import annotations

import ctypes
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="tb-sync-ui-"))
os.environ["TOKENBOARD_HOME"] = str(TMP / "home")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORT = 18924
DAV_ROOT = TMP / "dav"
Path(os.environ["TOKENBOARD_HOME"]).mkdir(parents=True, exist_ok=True)
DAV_ROOT.mkdir(parents=True, exist_ok=True)

ok_count = 0
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok_count
    if cond:
        ok_count += 1
        print(f"[ OK ] {name}")
    else:
        failures.append(name)
        print(f"[FAIL] {name}  {detail}")


def run(args, **kw):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(args, cwd=str(ROOT), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", **kw)


def wait_port(port: int, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.15)
    return False


def seed(n: int) -> None:
    code = f"""
from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.store import Store
from tokenboard.models import UsageRecord
ensure_dirs()
st = Store(DB_PATH)
st.upsert_usage([UsageRecord(app="codex", source="t", request_id="ui-%d" % i,
                            ts_ms=1760000000000 + i*1000, model="gpt-test",
                            input_tokens=10, output_tokens=5, cost_usd=0.0001)
                 for i in range({n})])
print(st.counts())
st.close()
"""
    r = run([sys.executable, "-c", code])
    if r.returncode != 0:
        raise RuntimeError(r.stdout + r.stderr)


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "fake_webdav.py"),
         "--root", str(DAV_ROOT), "--port", str(PORT)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        if not wait_port(PORT):
            print("[FAIL] 假 WebDAV 没起来")
            return 1
        seed(30)

        from tokenboard import sync as syncmod
        from tokenboard.config import DB_PATH
        from tokenboard.scanner import Scanner
        from tokenboard.store import Store
        from tokenboard.ui.panel import Panel
        from tokenboard.ui.syncwin import SyncWindow
        from tokenboard.ui.win32 import MSG, user32

        # 配好同步（指向假服务器）
        cfg = syncmod.load_config()
        cfg.url = f"http://127.0.0.1:{PORT}"
        cfg.username = "u"
        cfg.set_password("p")
        cfg.remote_dir = "TokenBoard"
        cfg.interval_min = 30
        cfg.enabled = True
        syncmod.save_config(cfg)

        store = Store(DB_PATH)

        # ---------------- 设置窗口 ----------------
        win = SyncWindow(store, on_changed=lambda: None)
        win.create()
        win.show()
        check("设置窗口创建成功", bool(win.hwnd))
        check("窗口回填了已保存的地址",
              "127.0.0.1" in win.edits["url"].get_text(), win.edits["url"].get_text())

        def pump(seconds: float, win_obj=None, panel_obj=None) -> None:
            msg = MSG()
            end = time.time() + seconds
            while time.time() < end:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                if win_obj is not None:
                    win_obj.on_timer(1)
                if panel_obj is not None:
                    panel_obj.on_timer(1)
                time.sleep(0.01)

        win._test()
        check("测试连接进入 busy 态", win.busy == "测试连接", win.busy)
        pump(6, win_obj=win)
        check("测试连接返回结果", "连接正常" in win.status, win.status)
        check("测试连接后 busy 已清空", win.busy == "", win.busy)

        win._sync_now()
        pump(6, win_obj=win)
        check("立即同步成功", win.status.startswith("✓"), win.status)
        remote = DAV_ROOT / "TokenBoard" / "usage.jsonl.gz"
        check("远端快照已生成", remote.is_file())

        # ---------------- 主面板 ----------------
        panel = Panel(store, Scanner(store))
        panel.create()
        panel.reload_sync()
        check("面板读到同步配置", panel._sync_cfg is not None and panel._sync_cfg.ready())
        panel._refresh_sync_note()
        check("面板底部有同步状态文字", bool(panel._sync_note), panel._sync_note)

        # 让面板跑一次强制同步（模拟托盘「立即同步」）
        started = panel.sync_now(force=True)
        check("面板触发同步成功", started)
        pump(6, panel_obj=panel)
        check("面板同步后状态正常", not panel._sync_failed, panel._sync_note)
        check("面板状态里有时间", "云同步" in panel._sync_note, panel._sync_note)

        # 断网场景：状态应变成失败，而不是崩
        cfg = syncmod.load_config()
        cfg.url = "http://127.0.0.1:9/dav"
        syncmod.save_config(cfg)
        panel.reload_sync()
        panel.sync_now(force=True)
        pump(10, panel_obj=panel)
        check("连不上时面板标记失败", panel._sync_failed, panel._sync_note)

        for w in (win, panel):
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        store.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print()
    print(f"通过 {ok_count} 项" + ("" if not failures else f"，失败 {len(failures)} 项：{failures}"))
    if failures:
        print(f"临时目录: {TMP}")
        return 1
    shutil.rmtree(TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())