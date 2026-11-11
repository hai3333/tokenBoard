#!/usr/bin/env python3
"""一个够用的假 WebDAV 服务器，只给测试和本地调试用。

支持同步会用到的四个动作：GET / PUT / PROPFIND / MKCOL，
外加 ETag 和 If-Match（用来验证 412 冲突重试那条路径）。

    python tools/fake_webdav.py --root D:\\tmp\\dav --port 18923
"""
from __future__ import annotations

import argparse
import hashlib
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(".").resolve()


def _etag(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003 - 基类签名就是这个
        if os.environ.get("FAKE_DAV_VERBOSE"):
            print("[dav]", fmt % args)

    # ---------------------------------------------------------------- 工具
    def _resolve(self) -> Path:
        raw = urllib.parse.urlparse(self.path).path
        rel = urllib.parse.unquote(raw).strip("/")
        target = (ROOT / rel).resolve()
        # 防目录穿越（测试服务器也别留洞）
        if ROOT not in target.parents and target != ROOT:
            self.send_error(403)
            raise ValueError("outside root")
        return target

    def _send(self, code: int, body: bytes = b"", headers: dict | None = None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    # ---------------------------------------------------------------- 方法
    def do_GET(self):
        if not self._check_auth():
            return
        p = self._resolve()
        if not p.is_file():
            self._send(404)
            return
        data = p.read_bytes()
        self._send(200, data, {"ETag": '"%s"' % _etag(p),
                               "Content-Type": "application/octet-stream"})

    def do_PUT(self):
        if not self._check_auth():
            return
        p = self._resolve()
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else b""
        if_match = self.headers.get("If-Match")
        if if_match and p.is_file():
            cur = '"%s"' % _etag(p)
            if if_match != cur:
                self._send(412, b"precondition failed")
                return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        self._send(201, b"", {"ETag": '"%s"' % _etag(p)})

    def do_MKCOL(self):
        if not self._check_auth():
            return
        p = self._resolve()
        if p.exists():
            self._send(405)
            return
        p.mkdir(parents=True)
        self._send(201)

    def do_PROPFIND(self):
        if not self._check_auth():
            return
        p = self._resolve()
        if not p.exists():
            self._send(404)
            return
        depth = (self.headers.get("Depth") or "0").strip()
        base = urllib.parse.urlparse(self.path).path.rstrip("/")
        entries = [p]
        if depth == "1" and p.is_dir():
            entries += sorted(p.iterdir())
        parts = []
        for e in entries:
            href = base + ("/" + urllib.parse.quote(e.name) if e != p else "")
            if e.is_dir():
                href += "/"
                prop = "<d:resourcetype><d:collection/></d:resourcetype>"
            else:
                prop = ("<d:resourcetype/>"
                        f"<d:getcontentlength>{e.stat().st_size}</d:getcontentlength>"
                        f"<d:getetag>\"{_etag(e)}\"</d:getetag>")
            parts.append(f"<d:response><d:href>{href}</d:href>"
                         f"<d:propstat><d:prop>{prop}</d:prop>"
                         f"<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>")
        body = ('<?xml version="1.0" encoding="utf-8"?>'
                '<d:multistatus xmlns:d="DAV:">' + "".join(parts) + "</d:multistatus>")
        self._send(207, body.encode("utf-8"),
                   {"Content-Type": "application/xml; charset=utf-8"})

    # Basic 认证：测试服务器一律放行，但要求客户端确实带上了头
    def _check_auth(self) -> bool:
        if not os.environ.get("FAKE_DAV_REQUIRE_AUTH"):
            return True
        if (self.headers.get("Authorization") or "").startswith("Basic "):
            return True
        self._send(401, b"auth required", {"WWW-Authenticate": 'Basic realm="test"'})
        return False


def main() -> int:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--port", type=int, default=18923)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    ROOT = Path(args.root).resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"fake webdav on http://{args.host}:{args.port}  root={ROOT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())