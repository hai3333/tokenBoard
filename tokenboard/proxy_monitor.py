"""只读 FlClash/Mihomo 的 OpenAI 策略组连接，供桌面小框显示。

速率由连续两次活动连接计数的差值计算；两次采样之间就结束的连接无法统计。
控制接口只连接本机，并从 FlClash 偏好中读取密钥，不记录请求或凭据。
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

GROUP = os.environ.get("TOKENBOARD_PROXY_GROUP", "openAI").strip() or "openAI"
RATE_INTERVAL = 1.5
DELAY_INTERVAL = 60.0
DELAY_TARGET = "https://chatgpt.com/"
_MAX_RESPONSE = 4 * 1024 * 1024


@dataclass(frozen=True)
class Controller:
    host: str
    port: int
    secret: str = field(repr=False)


@dataclass(frozen=True)
class NetworkState:
    status: str = "连接中"
    selected: str = ""
    delay_ms: int | None = None
    upload_bps: float | None = None
    download_bps: float | None = None


class ControllerError(Exception):
    """仅携带可展示的简短状态，绝不包含接口响应或密钥。"""


def read_controller() -> Controller:
    """读取 FlClash 当前生效的控制地址和密钥，不使用过期的生成配置。"""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ControllerError("未找到 FlClash")
    path = Path(appdata) / "com.follow" / "clash" / "shared_preferences.json"
    try:
        pref = json.loads(path.read_text(encoding="utf-8"))
        config = pref["flutter.config"]
        if isinstance(config, str):
            config = json.loads(config)
        patch = config["patchClashConfig"]
        address = str(patch.get("external-controller") or "").strip()
        secret = str(patch.get("secret") or "")
    except (OSError, ValueError, KeyError, TypeError):
        raise ControllerError("未找到 FlClash") from None
    if not address:
        raise ControllerError("请开启外部控制器")
    if not secret:
        raise ControllerError("请设置控制器密钥")
    try:
        parsed = urlsplit("//" + address)
        host, port = parsed.hostname or "", parsed.port
        if host.lower() == "localhost":
            host = "127.0.0.1"
        if not ipaddress.ip_address(host).is_loopback or not port:
            raise ValueError("not loopback")
    except ValueError:
        raise ControllerError("控制器地址不是本机") from None
    return Controller(host, port, secret)


def _get_json(controller: Controller, path: str, timeout: float = 3.0) -> dict:
    """绕过系统代理直连本机，只发 GET；限制响应大小。"""
    conn = http.client.HTTPConnection(controller.host, controller.port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Authorization": "Bearer " + controller.secret,
                                           "Accept": "application/json"})
        response = conn.getresponse()
        if response.status in (401, 403):
            raise ControllerError("控制器认证失败")
        if response.status == 404:
            raise ControllerError("未找到 OpenAI 策略组")
        if response.status != 200:
            raise ControllerError("控制器暂不可用")
        raw = response.read(_MAX_RESPONSE + 1)
        if len(raw) > _MAX_RESPONSE:
            raise ControllerError("控制器响应过大")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ControllerError("控制器响应异常")
        return result
    except ControllerError:
        raise
    except (OSError, ValueError, http.client.HTTPException):
        raise ControllerError("控制器暂不可用") from None
    finally:
        conn.close()


class RateSampler:
    """按连接 ID 求差，避免连接退出时整体计数回退造成假负数。"""

    def __init__(self, group: str = GROUP):
        self.group = group.casefold()
        self.previous: dict[str, tuple[int, int]] | None = None
        self.previous_at = 0.0

    def update(self, connections: list[dict], now: float) -> tuple[float, float] | None:
        current: dict[str, tuple[int, int]] = {}
        for item in connections:
            if not isinstance(item, dict):
                continue
            chains = item.get("chains") or []
            if not isinstance(chains, list) or not any(
                    str(name).casefold() == self.group for name in chains):
                continue
            ident = str(item.get("id") or "")
            if not ident:
                continue
            try:
                up = max(0, int(item.get("upload") or 0))
                down = max(0, int(item.get("download") or 0))
            except (TypeError, ValueError, OverflowError):
                continue
            current[ident] = (up, down)
        result = None
        elapsed = now - self.previous_at
        if self.previous is not None and elapsed > 0:
            up_delta = down_delta = 0
            for ident, (up, down) in current.items():
                old_up, old_down = self.previous.get(ident, (0, 0))
                up_delta += max(0, up - old_up)
                down_delta += max(0, down - old_down)
            result = (up_delta / elapsed, down_delta / elapsed)
        self.previous, self.previous_at = current, now
        return result


class ProxyMonitor:
    """后台采样：界面线程只读取不可变快照。"""

    def __init__(self, group: str = GROUP):
        self.group = group
        self._state = NetworkState()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._started = False

    def snapshot(self) -> NetworkState:
        with self._lock:
            return self._state

    def _set(self, **changes) -> None:
        with self._lock:
            self._state = replace(self._state, **changes)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._rate_loop, name="proxy-rate", daemon=True).start()
        threading.Thread(target=self._delay_loop, name="proxy-delay", daemon=True).start()

    def close(self) -> None:
        self._stop.set()

    def _group_path(self, group: str | None = None) -> str:
        return "/proxies/" + quote(group or self.group, safe="")

    def _rate_loop(self) -> None:
        sampler = RateSampler(self.group)
        previous_controller = None
        last_group_check = float("-inf")
        while not self._stop.is_set():
            try:
                controller = read_controller()
                if controller != previous_controller:
                    sampler = RateSampler(self.group)
                    previous_controller = controller
                    last_group_check = float("-inf")
                now = time.monotonic()
                if now - last_group_check >= 30:
                    _get_json(controller, self._group_path())
                    last_group_check = now
                payload = _get_json(controller, "/connections")
                connections = payload.get("connections") or []
                if not isinstance(connections, list):
                    raise ControllerError("控制器响应异常")
                rate = sampler.update(connections, time.monotonic())
                self._set(status="正常", upload_bps=rate[0] if rate else None,
                          download_bps=rate[1] if rate else None)
            except ControllerError as exc:
                sampler = RateSampler(self.group)
                previous_controller = None
                self._set(status=str(exc), selected="", delay_ms=None,
                          upload_bps=None, download_bps=None)
            self._stop.wait(RATE_INTERVAL)

    def _delay_loop(self) -> None:
        while not self._stop.is_set():
            try:
                controller = read_controller()
                selected = ""
                name = self.group
                seen: set[str] = set()
                # 跟随 selector / 自动选择组，展示实际使用的节点名称。
                for _ in range(6):
                    if name in seen:
                        break
                    seen.add(name)
                    info = _get_json(controller, self._group_path(name))
                    next_name = info.get("now")
                    if not isinstance(next_name, str) or not next_name:
                        break
                    selected = name = next_name
                query = urlencode({"url": DELAY_TARGET, "timeout": 8000})
                result = _get_json(controller, self._group_path() + "/delay?" + query,
                                   timeout=10.0)
                delay = int(result.get("delay") or 0)
                self._set(selected=selected, delay_ms=delay if delay > 0 else None)
            except (ControllerError, TypeError, ValueError, OverflowError):
                self._set(selected="", delay_ms=None)
            self._stop.wait(DELAY_INTERVAL)
