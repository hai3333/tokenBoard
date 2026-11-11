"""策略组速率与控制器对接回归，不访问真实代理或用户凭据。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tokenboard import proxy_monitor as pm  # noqa: E402


def connection(ident, up, down, chains):
    return {"id": ident, "upload": up, "download": down, "chains": chains}


class RateSamplerTests(unittest.TestCase):
    def test_only_group_deltas_are_counted(self):
        sampler = pm.RateSampler("openAI")
        first = [connection("a", 100, 300, ["node", "openAI"]),
                 connection("other", 3000, 7000, ["other"])]
        self.assertIsNone(sampler.update(first, 10))
        second = [connection("a", 160, 500, ["node", "OPENAI"]),
                  connection("b", 10, 30, ["openAI"]),
                  connection("other", 9000, 8000, ["other"])]
        self.assertEqual(sampler.update(second, 12), (35, 115))
        # 已消失的连接不造成负速率；重新计数也不会显示负值。
        self.assertEqual(sampler.update([connection("b", 5, 10, ["openAI"])], 14), (0, 0))
        self.assertEqual(sampler.update([], 16), (0, 0))

    def test_local_controller_validation_and_secret_is_not_repr(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"APPDATA": tmp}):
            folder = Path(tmp) / "com.follow" / "clash"
            folder.mkdir(parents=True)
            path = folder / "shared_preferences.json"

            def save(address, secret):
                config = {"patchClashConfig": {"external-controller": address,
                                                "secret": secret}}
                path.write_text(json.dumps({"flutter.config": json.dumps(config)}),
                                encoding="utf-8")

            save("127.0.0.1:9090", "fixture-secret")
            controller = pm.read_controller()
            self.assertEqual((controller.host, controller.port), ("127.0.0.1", 9090))
            self.assertNotIn("fixture-secret", repr(controller))
            save("192.0.2.10:9090", "fixture-secret")
            with self.assertRaises(pm.ControllerError):
                pm.read_controller()
            save("127.0.0.1:9090", "")
            with self.assertRaises(pm.ControllerError):
                pm.read_controller()


class FakeHandler(BaseHTTPRequestHandler):
    counter = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer fixture-secret":
            self.send_response(401)
            self.end_headers()
            return
        path = urlsplit(self.path).path
        if path == "/proxies/openAI/delay":
            payload = {"delay": 123}
        elif path == "/proxies/openAI":
            payload = {"now": "auto"}
        elif path == "/proxies/auto":
            payload = {"now": "node"}
        elif path == "/proxies/node":
            payload = {"type": "Shadowsocks"}
        elif path == "/connections":
            type(self).counter += 1
            n = type(self).counter
            payload = {"connections": [connection("a", n * 100, n * 200,
                                                   ["node", "openAI"])]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ControllerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_authenticated_reads_and_background_monitor(self):
        host, port = self.server.server_address
        cfg = pm.Controller(host, port, "fixture-secret")
        with self.assertRaises(pm.ControllerError):
            pm._get_json(pm.Controller(host, port, "wrong"), "/connections")
        with patch.object(pm, "read_controller", return_value=cfg), \
                patch.object(pm, "RATE_INTERVAL", 0.05), \
                patch.object(pm, "DELAY_INTERVAL", 0.15):
            monitor = pm.ProxyMonitor("openAI")
            monitor.start()
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    state = monitor.snapshot()
                    if state.delay_ms and state.upload_bps is not None:
                        break
                    time.sleep(0.02)
                self.assertEqual(state.status, "正常")
                self.assertEqual(state.selected, "node")
                self.assertEqual(state.delay_ms, 123)
                self.assertGreater(state.upload_bps, 0)
                self.assertGreater(state.download_bps, state.upload_bps)
            finally:
                monitor.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
