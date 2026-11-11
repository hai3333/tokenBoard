"""极简 WebDAV 客户端：只做同步用得到的那几个动作。

为什么不引第三方库：项目唯一的第三方依赖是 zstandard，为了
GET/PUT/PROPFIND/MKCOL 这几个动作去装 webdavclient3 + lxml，安装包会从
10MB 涨到 30MB 以上，不值当。这里用 urllib 手写，行为完全可控。

网络上的坑（都按「宁可报错也不要静默失败」处理）：
  * 认证走 Basic —— 先带 Authorization 再发，避免多一次 401 往返；
  * 路径逐段 quote，中文/空格目录名不会把 URL 弄坏；
  * 坚果云这类服务对同名文件 PUT 会直接覆盖（不带 If-Match 时），
    需要并发保护就带 ETag；
  * 5xx 和连接重置重试两次，4xx 是明确错误不重试。
"""
from __future__ import annotations

import base64
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# 默认超时：NAS 走公网时 20 秒够用，又不至于把界面卡死太久
DEFAULT_TIMEOUT = 20


class WebDAVError(Exception):
    """WebDAV 层错误：带上 HTTP 状态码，方便界面区分「认证失败」和「网络不通」。"""

    def __init__(self, status: int, message: str, url: str = ""):
        self.status = status
        self.message = message
        self.url = url
        super().__init__(message)

    def friendly(self) -> str:
        """给界面看的一句话。"""
        if self.status in (401, 403):
            return f"认证失败（HTTP {self.status}）：账号或密码不对，或者没有该目录的权限"
        if self.status == 404:
            return "远端路径不存在（HTTP 404）"
        if self.status == 507:
            return "远端空间不足（HTTP 507）"
        if self.status == 0:
            return f"连不上服务器：{self.message}"
        return f"HTTP {self.status}：{self.message}"


def _quote_path(path: str) -> str:
    """把 'a/b/中文 目录' 逐段转义成 URL 片段。"""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p]
    return "/".join(urllib.parse.quote(p, safe="") for p in parts)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code == 429
    return True          # URLError / 超时 / 连接重置都值得重试


class WebDAV:
    """一个 WebDAV 连接。所有方法返回 (status, data)，失败抛 WebDAVError。"""

    def __init__(self, base_url: str, username: str = "", password: str = "",
                 timeout: int = DEFAULT_TIMEOUT, attempts: int = 3,
                 insecure: bool = False):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self._ctx = None
        if insecure:
            # 自签证书的 NAS：只在用户明确勾选时才放行
            self._ctx = ssl.create_default_context()
            self._ctx.check_hostname = False
            self._ctx.verify_mode = ssl.CERT_NONE

    # ------------------------------------------------------------------
    def url_for(self, path: str) -> str:
        if not self.base_url:
            raise WebDAVError(0, "服务器地址为空")
        q = _quote_path(path)
        return f"{self.base_url}/{q}" if q else self.base_url

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"User-Agent": "TokenBoard/1.0 (WebDAV sync)"}
        if self.username:
            raw = f"{self.username}:{self.password}".encode("utf-8")
            h["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        if extra:
            h.update(extra)
        return h

    # ------------------------------------------------------------------
    def request(self, method: str, path: str, body: bytes | None = None,
                headers: dict | None = None) -> tuple[int, bytes, dict]:
        """发一次请求，返回 (状态码, 响应体, 响应头)。"""
        url = self.url_for(path)
        last: Exception | None = None
        for i in range(self.attempts):
            try:
                req = urllib.request.Request(
                    url, data=body, method=method,
                    headers=self._headers(headers))
                with urllib.request.urlopen(req, timeout=self.timeout,
                                            context=self._ctx) as r:
                    return r.status, r.read(), dict(r.headers)
            except urllib.error.HTTPError as e:
                # 4xx 是明确结果，交给调用方判断；5xx/429 才值得重试
                if e.code < 500 and e.code != 429:
                    detail = ""
                    try:
                        detail = e.read().decode("utf-8", "replace")[:200]
                    except Exception:  # noqa: BLE001
                        pass
                    raise WebDAVError(e.code, detail or e.reason,
                                      url) from e
                last = e
            except Exception as e:  # noqa: BLE001
                last = e
            if i < self.attempts - 1:
                time.sleep(0.6 * (i + 1))
        if isinstance(last, urllib.error.HTTPError):
            raise WebDAVError(last.code, str(last.reason), url)
        raise WebDAVError(0, str(last), url)

    # ------------------------------------------------------------------
    def get(self, path: str) -> tuple[bytes, str]:
        """下载一个文件，返回 (内容, ETag)。404 抛 WebDAVError(404)。"""
        status, data, headers = self.request("GET", path)
        if status not in (200, 206):
            raise WebDAVError(status, "下载失败", self.url_for(path))
        return data, (headers.get("ETag") or headers.get("etag") or "")

    def put(self, path: str, data: bytes, if_match: str | None = None) -> str:
        """上传一个文件，返回新 ETag。

        if_match 给了就带 If-Match：远端在下载之后被别人改过会返回 412，
        调用方据此重新合并一次，避免把别人刚写的数据覆盖掉。
        """
        headers = {"Content-Type": "application/octet-stream"}
        if if_match:
            headers["If-Match"] = if_match
        status, body, resp = self.request("PUT", path, body=data, headers=headers)
        if status not in (200, 201, 204):
            raise WebDAVError(status, body[:200].decode("utf-8", "replace") if body else "",
                              self.url_for(path))
        return resp.get("ETag") or resp.get("etag") or ""

    def propfind(self, path: str, depth: str = "0") -> tuple[int, list[dict]]:
        """列目录/查属性。返回 (状态码, [{href, length, etag, is_dir}, ...])。

        404 不抛异常，直接返回 (404, [])：调用方据此判断要不要建目录。
        """
        body = (b'<?xml version="1.0" encoding="utf-8"?>'
                b'<d:propfind xmlns:d="DAV:"><d:prop>'
                b'<d:resourcetype/><d:getcontentlength/><d:getetag/>'
                b'</d:prop></d:propfind>')
        try:
            status, data, _h = self.request(
                "PROPFIND", path, body=body,
                headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"})
        except WebDAVError as e:
            if e.status == 404:
                return 404, []
            raise
        if status not in (207, 200):
            return status, []
        return status, _parse_multistatus(data)

    def mkcol(self, path: str) -> int:
        """建目录。已存在（405）也算成功。"""
        try:
            status, _d, _h = self.request("MKCOL", path)
            return status
        except WebDAVError as e:
            if e.status in (405, 301):
                return e.status
            raise

    def ensure_dir(self, path: str) -> None:
        """逐级创建目录（MKCOL 不会自动建父目录）。"""
        parts = [p for p in str(path or "").strip("/").split("/") if p]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            status, _items = self.propfind(cur)
            if status == 207:
                continue
            if status == 404:
                st = self.mkcol(cur)
                if st not in (201, 200, 405):
                    raise WebDAVError(st, "创建目录失败", self.url_for(cur))

    def exists(self, path: str) -> bool:
        try:
            status, items = self.propfind(path)
            return status == 207 and bool(items)
        except WebDAVError:
            return False


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def _parse_multistatus(data: bytes) -> list[dict]:
    """解析 PROPFIND 的 XML，抽出 href / 长度 / ETag / 是否目录。

    不用 lxml：标准库 ElementTree 足够，也省一个打包依赖。
    """
    out: list[dict] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return out
    for resp in root:
        if _strip_ns(resp.tag) != "response":
            continue
        item = {"href": "", "length": 0, "etag": "", "is_dir": False}
        for node in resp.iter():
            name = _strip_ns(node.tag)
            text = (node.text or "").strip()
            if name == "href":
                item["href"] = urllib.parse.unquote(text)
            elif name == "getcontentlength":
                try:
                    item["length"] = int(text or 0)
                except ValueError:
                    pass
            elif name == "getetag":
                item["etag"] = text.strip('"')
            elif name == "resourcetype":
                item["is_dir"] = len(list(node)) > 0
        if item["href"]:
            out.append(item)
    return out


def find_file(items: list[dict], name: str) -> dict | None:
    """在 PROPFIND 结果里按文件名找一项（远端返回的是完整 href）。"""
    for it in items:
        if it["href"].rstrip("/").endswith("/" + name) or it["href"].rstrip("/") == name:
            return it
    return None