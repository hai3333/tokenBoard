"""单实例 + 二次启动唤起窗口。

做法：本机开一个极小的 TCP 端口作为 IPC。
  - 启动时先尝试连接：连上说明已有实例 -> 发一条 "show" 并退出
  - 连不上 -> 自己起一个监听线程，收到 "show" 就让面板弹出来
这样「找不到窗口」的问题就不存在了：再点一次启动图标即可唤回。
"""
from __future__ import annotations

import os
import socket
import threading

HOST = "127.0.0.1"
# 测试用：TOKENBOARD_IPC_PORT 可覆盖端口，避免和已运行实例抢单实例端口
PORT = int(os.environ.get("TOKENBOARD_IPC_PORT", "42733"))


def _send(msg: bytes) -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1.5) as s:
            s.sendall(msg)
            return True
    except OSError:
        return False


def notify_existing(msg: bytes = b"show\n") -> bool:
    """如果有实例在跑，通知它做事，返回 True。"""
    return _send(msg)


class Server:
    """监听端口：收到 show 让面板弹出来，收到 sync 打开同步设置。"""

    def __init__(self, on_show, on_settings=None):
        self.on_show = on_show
        self.on_settings = on_settings
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen(4)
            s.settimeout(1.0)
        except OSError:
            return False
        self._sock = s
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                data = conn.recv(64)
                if b"sync" in data:
                    if self.on_settings is not None:
                        self.on_settings()
                elif b"show" in data:
                    self.on_show()
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
