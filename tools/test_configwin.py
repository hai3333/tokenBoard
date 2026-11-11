#!/usr/bin/env python3
"""配置窗口功能测试（全程用临时目录，不碰用户真实配置）。

覆盖：
1. 列表选中 -> 表单联动
2. 保存 -> 落库（密钥加密）
3. 设为默认 -> 写 opencode.jsonc（临时文件）
4. 拉模型目录 -> 对着本地假服务端拉
5. 连通性测试 -> 对着本地假服务端发最小请求
6. 导入 ccswitch -> 只读导入
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.providers import ProviderStore
from tokenboard.ui.configwin import ConfigWindow
from tokenboard.ui.win32 import MSG, user32

FAIL = []

PM_REMOVE = 0x0001


def pump(seconds: float):
    """转消息循环。

    真机上主面板的 run() 在跑，WM_TIMER 有人处理；
    测试脚本没有消息循环，on_timer 根本不会被调用，
    后台线程的结果自然也就没人接。
    """
    msg = MSG()
    end = time.time() + seconds
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.02)


def check(name: str, cond: bool, extra: str = ""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


class FakeStore:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        import threading as th
        self._lock = th.RLock()


class FakeAPI(BaseHTTPRequestHandler):
    """极简的 OpenAI 兼容服务：/models 与 /chat/completions。"""
    calls: list = []

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeAPI.calls.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path.endswith("/models"):
            self._json({"data": [{"id": "m-1"}, {"id": "m-2"}, {"id": "m-3"}]})
        else:
            self._json({"error": "nope"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        FakeAPI.calls.append(("POST", self.path, self.headers.get("Authorization")))
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            payload = {}
        if self.path.endswith("/chat/completions"):
            if self.headers.get("Authorization") != "Bearer sk-test-key":
                self._json({"error": "bad key"}, 401)
                return
            self._json({"choices": [{"message": {"content": "hi"}}],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 2}})
        else:
            self._json({"error": "nope"}, 404)


def click(win, key):
    x, y, w, h = win._rects[key]
    win.on_click(x + w / 2, y + h / 2)


def wait_idle(win, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        pump(0.1)
        if not win.busy:
            pump(0.3)      # 再转几圈，让 on_timer 把结果取走
            return True
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tb_cfg_"))
    try:
        cfg = tmp / "opencode.jsonc"
        cfg.write_text(json.dumps({
            "model": "old/model",
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                "hs": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "火山",
                    "options": {"baseURL": "http://127.0.0.1:1/v1",
                                "apiKey": "sk-old", "setCacheKey": True},
                    "models": {"m-1": {"name": "m-1"}},
                },
            },
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        store = ProviderStore(FakeStore(tmp / "tb.db"), config_path=cfg)
        win = ConfigWindow(store)
        win.create()
        win.show()
        time.sleep(0.6)
        win.reload()

        print("[1] 导入 + 列表联动")
        n = store.import_from_opencode_config(cfg)
        win.reload()
        check("导入 1 个 provider", n == 1 and len(win.providers) == 1)
        check("表单填上了名称", win.edits["name"].get_text() == "火山",
              win.edits["name"].get_text())
        check("表单填上了 baseURL",
              win.edits["base"].get_text() == "http://127.0.0.1:1/v1")

        print("\n[2] 保存（改名称 + 改 key）")
        win.edits["name"].set_text("火山改")
        win.edits["key"].set_text("sk-new-key")
        click(win, "btn_save")
        time.sleep(0.3)
        p = store.get("hs")
        check("名称已落库", p is not None and p.name == "火山改", p.name if p else "")
        check("密钥已落库", p is not None and p.api_key == "sk-new-key")
        enc = store.conn.execute(
            "SELECT api_key_enc FROM oc_providers WHERE id='hs'").fetchone()["api_key_enc"]
        check("库里是密文", "sk-new-key" not in enc)

        print("\n[3] 设为默认 -> 写 opencode.jsonc")
        click(win, "btn_apply")
        time.sleep(0.4)
        back = json.loads(cfg.read_text(encoding="utf-8"))
        check("model 字段已写", back.get("model") == "hs/m-1", back.get("model"))
        check("provider 已投影", "hs" in back.get("provider", {}))
        check("密钥写回明文（OpenCode 要的就是明文）",
              back["provider"]["hs"]["options"]["apiKey"] == "sk-new-key")
        check("$schema 保留", back.get("$schema") == "https://opencode.ai/config.json")

        print("\n[4] 拉模型目录（本地假服务端）")
        srv = HTTPServer(("127.0.0.1", 0), FakeAPI)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}/v1"
        win.edits["base"].set_text(base)
        win.edits["key"].set_text("sk-test-key")
        click(win, "btn_fetch")
        wait_idle(win)
        time.sleep(0.4)
        models_text = win.edits["models"].get_text()
        check("模型列表已填进输入框", "m-1" in models_text and "m-3" in models_text,
              models_text.replace("\r\n", " ")[:70])
        check("带上了 Authorization",
              any(c[0] == "GET" and c[2] == "Bearer sk-test-key" for c in FakeAPI.calls))

        print("\n[5] 连通性测试")
        FakeAPI.calls.clear()
        win.edits["models"].set_text("m-1 m-1\r\nm-2 m-2")
        click(win, "btn_save")
        time.sleep(0.3)
        click(win, "btn_test")
        wait_idle(win)
        time.sleep(0.4)
        check("测试通过", win.status_kind == "ok" and "连接正常" in win.status,
              f"{win.status_kind}: {win.status}")
        check("真的发了请求",
              any(c[0] == "POST" for c in FakeAPI.calls))

        print("\n[6] 错误 key 会被识别")
        win.edits["key"].set_text("sk-wrong")
        click(win, "btn_test")
        wait_idle(win)
        time.sleep(0.4)
        check("鉴权失败有明确提示", win.status_kind == "err" and "鉴权" in win.status,
              win.status)

        print("\n[7] 新增 / 删除")
        click(win, "btn_add")
        time.sleep(0.3)
        check("新增后多一个 provider", len(store.list()) == 2, str(len(store.list())))
        new_id = win.sel
        click(win, "btn_del")
        time.sleep(0.3)
        check("删除后少一个", len(store.list()) == 1, str(len(store.list())))
        check("删的就是刚建的那个",
              all(p.id != new_id for p in store.list()))

        print("\n[8] 导入 ccswitch（只读）")
        ccdb = Path.home() / ".cc-switch" / "cc-switch.db"
        if ccdb.exists():
            before = ccdb.stat().st_mtime
            click(win, "btn_imp_cc")
            time.sleep(0.6)
            check("导入成功", len(store.list()) > 1, f"{len(store.list())} 个")
            check("cc-switch.db 未被改动", ccdb.stat().st_mtime == before)
        else:
            print("  -- 没装 ccswitch，跳过")

        srv.shutdown()
        win.destroy()
        time.sleep(0.3)

        print()
        if FAIL:
            print(f"!!! {len(FAIL)} 项失败: {FAIL}")
            return 1
        print("全部通过")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

