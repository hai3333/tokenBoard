"""WebDAV 双向同步：本机用量 <-> 远端快照。

为什么是「双向合并」而不是「上传备份」
--------------------------------------
需求是多台机器的看板能合在一起看（家里 + 公司、笔记本 + 台式）。
所以每次同步做三件事：

    下载远端快照 -> 按唯一键并入本地（已有的不覆盖）
                -> 把本地全量重新打包 -> 传回远端

唯一键沿用数据库里的约束：用量 (app, request_id)、速度 (app, sample_id)。
重复合并是幂等的，所以「多传一次」不会把数字刷大，这一点比什么增量
游标都省心。

并发
----
两台机器同时同步时，后传的会把先传的覆盖掉。下载时记住 ETag，上传时带
If-Match；远端在这期间被改过会返回 412，这时重新下载合并再传一次，最多
三轮。没有 ETag 的服务器（部分 NAS）就退化成「后写覆盖」，但下一次同步
会用自己的全量数据把它补齐，最终还是一致的。

只传什么
--------
只有 usage_events 和 speed_samples。不含任何 API Key、不含 collector 配置、
不含同步密码本身 —— 那份配置只存在本机（密码过 DPAPI）。
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field

from . import dpapi
from .config import SYNC_CONFIG_PATH
from .webdav import WebDAV, WebDAVError, find_file

log = logging.getLogger("tokenboard.sync")

SNAPSHOT_VERSION = 1
REMOTE_FILENAME = "usage.jsonl.gz"
MAX_ATTEMPTS = 3          # 412 冲突时重新合并的轮数上限


# ---------------------------------------------------------------- 配置
@dataclass
class SyncConfig:
    """同步配置。密码加密后落盘，明文只在内存里出现。"""

    enabled: bool = False
    url: str = ""
    username: str = ""
    password_enc: str = ""
    remote_dir: str = "TokenBoard"
    interval_min: int = 30
    timeout_sec: int = 20
    insecure: bool = False          # 自签证书的 NAS 才用
    last_sync_at: int = 0           # 最近一次成功同步（epoch ms）
    last_status: str = "never"      # never / ok / error / skipped
    last_error: str = ""
    last_error_at: int = 0
    etag: str = ""
    fingerprint: dict = field(default_factory=dict)
    last_remote_bytes: int = 0
    last_remote_count: int = 0

    # ---- 密码：只在内存里明文 ----
    @property
    def password(self) -> str:
        if not self.password_enc:
            return ""
        try:
            return dpapi.unprotect(self.password_enc)
        except Exception:  # noqa: BLE001
            return ""

    def set_password(self, plain: str) -> None:
        self.password_enc = dpapi.protect(plain) if plain else ""

    def ready(self) -> bool:
        return bool(self.enabled and self.url.strip())

    def remote_path(self) -> str:
        d = (self.remote_dir or "TokenBoard").strip().strip("/")
        return f"{d}/{REMOTE_FILENAME}" if d else REMOTE_FILENAME

    def masked_password(self) -> str:
        return dpapi.mask(self.password)


def load_config() -> SyncConfig:
    """读配置；文件不存在/坏了都当「未配置」，不抛异常。"""
    try:
        raw = SYNC_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return SyncConfig()
    if not isinstance(data, dict):
        return SyncConfig()
    known = {f for f in SyncConfig.__dataclass_fields__}
    cfg = SyncConfig(**{k: v for k, v in data.items() if k in known})
    # 类型兜底：手改配置文件写错类型不该让整个程序崩
    for name in ("interval_min",):
        try:
            setattr(cfg, name, max(1, int(getattr(cfg, name) or 1)))
        except Exception:  # noqa: BLE001
            setattr(cfg, name, 30)
    return cfg


def save_config(cfg: SyncConfig) -> None:
    """原子写：先写临时文件再替换，避免界面上读到半个 JSON。"""
    SYNC_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    tmp = SYNC_CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SYNC_CONFIG_PATH)


def is_due(cfg: SyncConfig, now_ms: int | None = None) -> bool:
    """到点了吗（按 interval_min 判断）。

    判断基准取「最近一次尝试」：成功用 last_sync_at，失败用 last_error_at。
    取两者较晚的那个 —— 否则失败的机器会每分钟重试一次，把服务器打爆，
    而用户看到的只是「一直在失败」。
    """
    if not cfg.ready():
        return False
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    base = cfg.last_sync_at or 0
    if cfg.last_error_at:
        base = max(base, cfg.last_error_at)
    if not base:
        return True
    return now - base >= max(1, cfg.interval_min) * 60_000


# ---------------------------------------------------------------- 快照
def _device_id(store) -> str:
    """本机设备 id（同时也是快照里的来源标记，方便排查是谁把数据传上来的）。"""
    did = store.get_meta("device_id") or ""
    if not did:
        did = uuid.uuid4().hex
        store.set_meta("device_id", did)
    return str(did)


def build_snapshot(store) -> bytes:
    """把整个库打包成 gzip JSONL。

    用独立只读连接遍历，避免长时间占着主连接的锁（导出可能扫几十万行）。
    """
    conn = store.open_reader()
    buf = io.BytesIO()
    try:
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6, mtime=0) as gz:
            def line(obj: dict) -> None:
                gz.write(json.dumps(obj, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8"))
                gz.write(b"\n")

            n_u = n_s = 0
            header = {"k": "meta", "v": SNAPSHOT_VERSION,
                      "device": _device_id(store), "at": int(time.time() * 1000)}
            gz.write(json.dumps(header, ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8") + b"\n")

            for r in store.iter_usage_rows(conn):
                n_u += 1
                line({
                    "k": "u",
                    "a": r[0], "s": r[1], "r": r[2], "t": r[3], "d": r[4],
                    "m": r[5], "i": r[6], "o": r[7], "cr": r[8], "cw": r[9],
                    "rt": r[10], "tt": r[11], "c": r[12], "ss": r[13], "p": r[14],
                })
            for r in store.iter_speed_rows(conn):
                n_s += 1
                line({
                    "k": "s",
                    "a": r[0], "s": r[1], "id": r[2], "t": r[3], "d": r[4],
                    "m": r[5], "kd": r[6], "tf": r[7], "du": r[8], "o": r[9],
                })
            # 行数写在最后一行 meta 里：解析时后者覆盖前者，读的一方就能
            # 不展开明细也知道远端有多少条（界面/CLI 显示用）
            line({"k": "meta", "v": SNAPSHOT_VERSION,
                  "device": header["device"], "at": header["at"],
                  "n_usage": n_u, "n_speed": n_s})
    finally:
        conn.close()
    log.info("快照打包完成：%d 条用量 / %d 条速度采样，%.1f KB",
             n_u, n_s, len(buf.getvalue()) / 1024)
    return buf.getvalue()


def _num(v, cast=int):
    try:
        return cast(v or 0)
    except (TypeError, ValueError):
        return cast(0)


def parse_snapshot(raw: bytes) -> tuple[dict, list[tuple], list[tuple]]:
    """解析快照，返回 (头部, 用量行, 速度行)。

    容忍坏数据：单行解析失败就跳过，不因为一条脏记录整次同步失败。
    """
    header: dict = {}
    usage: list[tuple] = []
    speed: list[tuple] = []
    if not raw:
        return header, usage, speed
    try:
        text = gzip.decompress(raw).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        # 不是 gzip 就当纯 JSONL（手工放上去的旧文件也能读）
        text = raw.decode("utf-8", "replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(o, dict):
            continue
        k = o.get("k")
        if k == "meta":
            header = o
        elif k == "u":
            usage.append((
                str(o.get("a") or ""), str(o.get("s") or ""), str(o.get("r") or ""),
                _num(o.get("t")), str(o.get("d") or ""), str(o.get("m") or ""),
                _num(o.get("i")), _num(o.get("o")), _num(o.get("cr")), _num(o.get("cw")),
                _num(o.get("rt")), _num(o.get("tt")), _num(o.get("c"), float),
                str(o.get("ss") or ""), str(o.get("p") or ""),
            ))
        elif k == "s":
            speed.append((
                str(o.get("a") or ""), str(o.get("s") or ""), str(o.get("id") or ""),
                _num(o.get("t")), str(o.get("d") or ""), str(o.get("m") or ""),
                str(o.get("kd") or "call"), _num(o.get("tf")), _num(o.get("du")),
                _num(o.get("o")),
            ))
    return header, usage, speed


# ---------------------------------------------------------------- 同步
@dataclass
class SyncResult:
    """一次同步的结果，界面/CLI/日志共用。"""

    ok: bool = False
    skipped: bool = False
    error: str = ""
    applied_usage: int = 0        # 从远端新增的用量条数
    applied_speed: int = 0
    uploaded: bool = False
    remote_exists: bool = False
    remote_bytes: int = 0
    remote_count: int = 0         # 远端快照里的用量条数（头部记录）
    local_usage: int = 0
    local_speed: int = 0
    duration_ms: int = 0
    at_ms: int = 0

    def summary(self) -> str:
        """一行中文结论，托盘/面板/CLI 都能直接用。"""
        if self.skipped:
            return self.error or "未启用"
        if not self.ok:
            return f"同步失败：{self.error}"
        bits = []
        if self.applied_usage or self.applied_speed:
            bits.append(f"下载 {self.applied_usage + self.applied_speed} 条")
        if self.uploaded:
            bits.append(f"上传 {self.local_usage + self.local_speed} 条")
        if not bits:
            bits.append("已是最新")
        return "、".join(bits)


def _make_client(cfg: SyncConfig) -> WebDAV:
    return WebDAV(cfg.url, cfg.username, cfg.password,
                  timeout=max(5, int(cfg.timeout_sec or 20)),
                  insecure=bool(cfg.insecure))


def probe(cfg: SyncConfig) -> dict:
    """测试连接：只读，不改远端任何东西。

    返回 {"ok", "message", "remote_exists", "remote_bytes", "remote_count"}。
    """
    out = {"ok": False, "message": "", "remote_exists": False,
           "remote_bytes": 0, "remote_count": 0}
    if not cfg.url.strip():
        out["message"] = "服务器地址为空"
        return out
    try:
        dav = _make_client(cfg)
        dav.ensure_dir(cfg.remote_dir)
        status, items = dav.propfind(cfg.remote_dir, depth="1")
        if status != 207:
            out["message"] = f"目录列不出来（HTTP {status}）"
            return out
        out["ok"] = True
        item = find_file(items, REMOTE_FILENAME)
        if item:
            out["remote_exists"] = True
            out["remote_bytes"] = int(item.get("length") or 0)
            try:
                raw, _etag = dav.get(cfg.remote_path())
                _h, u, s = parse_snapshot(raw)
                out["remote_count"] = len(u) + len(s)
                out["remote_bytes"] = len(raw)
            except WebDAVError as e:
                out["message"] = f"能连上，但快照读不了：{e.friendly()}"
                return out
            out["message"] = (f"连接正常 · 远端已有快照 "
                              f"（{out['remote_count']:,} 条 / "
                              f"{out['remote_bytes'] / 1024:.1f} KB）")
        else:
            out["message"] = "连接正常 · 远端还没有快照，第一次同步会创建"
        return out
    except WebDAVError as e:
        out["message"] = e.friendly()
        return out
    except Exception as e:  # noqa: BLE001
        out["message"] = f"{type(e).__name__}: {e}"
        return out


def sync_once(store, cfg: SyncConfig | None = None,
              force: bool = False) -> SyncResult:
    """跑一次同步。失败不抛异常，结果全在 SyncResult 里。"""
    cfg = cfg or load_config()
    res = SyncResult(at_ms=int(time.time() * 1000))
    t0 = time.time()
    try:
        res.local_usage, res.local_speed = store.counts()
    except Exception:  # noqa: BLE001
        pass

    if not cfg.ready():
        res.skipped = True
        res.error = "未启用云同步或没填服务器地址"
        res.duration_ms = int((time.time() - t0) * 1000)
        return res

    dav = _make_client(cfg)
    try:
        dav.ensure_dir(cfg.remote_dir)

        for attempt in range(MAX_ATTEMPTS):
            remote_raw = b""
            etag = ""
            try:
                remote_raw, etag = dav.get(cfg.remote_path())
                res.remote_exists = True
                res.remote_bytes = len(remote_raw)
            except WebDAVError as e:
                if e.status != 404:
                    raise
            header, u_rows, s_rows = parse_snapshot(remote_raw)
            res.remote_count = _num(header.get("n_usage")) or len(u_rows) + len(s_rows)

            # 1) 远端 -> 本地
            res.applied_usage = store.import_usage_rows(u_rows)
            res.applied_speed = store.import_speed_rows(s_rows)
            res.local_usage, res.local_speed = store.counts()

            # 2) 本地有没有新东西要传：导入过远端数据也算「有变化」
            fp = store.data_fingerprint()
            changed = (force or res.applied_usage or res.applied_speed
                       or not remote_raw or cfg.fingerprint != fp)
            if not changed:
                res.ok = True
                _save_ok(cfg, res, etag or cfg.etag, fp)
                res.duration_ms = int((time.time() - t0) * 1000)
                log.info("同步完成：双方一致，无需上传")
                return res

            # 3) 本地 -> 远端
            payload = build_snapshot(store)
            try:
                new_etag = dav.put(cfg.remote_path(), payload,
                                   if_match=etag or None)
            except WebDAVError as e:
                if e.status == 412 and attempt < MAX_ATTEMPTS - 1:
                    log.info("远端在同步期间被改过（412），重新合并后重试")
                    continue
                raise
            res.uploaded = True
            res.ok = True
            res.remote_bytes = len(payload)
            # 传完之后远端就是「本地这份」，条数以本地为准
            res.remote_count = res.local_usage + res.local_speed
            _save_ok(cfg, res, new_etag or "", store.data_fingerprint())
            res.duration_ms = int((time.time() - t0) * 1000)
            log.info("同步完成：下载 %d + %d 条，上传 %d 条（%.1f KB）",
                     res.applied_usage, res.applied_speed,
                     res.local_usage + res.local_speed, len(payload) / 1024)
            return res

        # 三轮都撞上 412：不报 ok，等下一轮再说
        raise WebDAVError(412, "远端持续被修改，稍后再试")

    except WebDAVError as e:
        res.ok = False
        res.error = e.friendly()
    except Exception as e:  # noqa: BLE001
        res.ok = False
        res.error = f"{type(e).__name__}: {e}"

    res.duration_ms = int((time.time() - t0) * 1000)
    cfg.last_status = "error"
    cfg.last_error = res.error
    cfg.last_error_at = res.at_ms
    try:
        save_config(cfg)
    except Exception:  # noqa: BLE001
        pass
    log.warning("同步失败：%s", res.error)
    return res


def _save_ok(cfg: SyncConfig, res: SyncResult, etag: str,
             fingerprint: dict | None = None) -> None:
    """记录一次成功同步。fingerprint 用「这次传上去的内容指纹」回填。"""
    cfg.last_sync_at = res.at_ms
    cfg.last_status = "ok"
    cfg.last_error = ""
    cfg.etag = etag
    cfg.last_remote_bytes = res.remote_bytes
    cfg.last_remote_count = res.remote_count
    if fingerprint is not None:
        cfg.fingerprint = fingerprint
    save_config(cfg)