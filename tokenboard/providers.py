"""OpenCode provider 的自建库：加密存密钥，切换时投影回 opencode.jsonc。

为什么不让 opencode.jsonc 当唯一数据源：
- 那份文件 ccswitch 也会写，两边都改就互相覆盖。
- 密钥明文躺在配置文件里，备份/同步/截图都会带出去。

所以这里的分工是：
    本库（tokenboard.db）  = 真相，密钥用 DPAPI 加密
    opencode.jsonc         = 投影，给 OpenCode 实际读取
两个导入源（不用手敲 key）：
    1. 现有 ~/.config/opencode/opencode.jsonc
    2. cc-switch.db（ccswitch 的 opencode provider）
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import dpapi, opencode_config as oc

SCHEMA = """
CREATE TABLE IF NOT EXISTS oc_providers (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL DEFAULT '',
    npm            TEXT NOT NULL DEFAULT '@ai-sdk/openai-compatible',
    base_url       TEXT NOT NULL DEFAULT '',
    api_key_enc    TEXT NOT NULL DEFAULT '',
    models_json    TEXT NOT NULL DEFAULT '{}',
    default_model  TEXT NOT NULL DEFAULT '',
    is_current     INTEGER NOT NULL DEFAULT 0,
    sort_index     INTEGER NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL DEFAULT 0,
    updated_at     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS oc_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class Provider:
    id: str
    name: str = ""
    npm: str = oc.DEFAULT_NPM
    base_url: str = ""
    api_key: str = ""            # 明文，只在内存里存在
    models: dict = field(default_factory=dict)
    default_model: str = ""
    is_current: bool = False
    sort_index: int = 0

    @property
    def masked_key(self) -> str:
        return dpapi.mask(self.api_key)

    def model_ids(self) -> list[str]:
        return list(self.models.keys()) if isinstance(self.models, dict) else []

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "npm": self.npm,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "models": self.models,
            "default_model": self.default_model,
            "is_current": self.is_current,
            "sort_index": self.sort_index,
        }


def _models_text(p: Provider) -> str:
    try:
        return json.dumps(p.models or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


def parse_models_text(text: str) -> dict:
    """把「一行一个 模型id  显示名」解析成 OpenCode 的 models 结构。

    已有模型的附加字段（reasoning / limit / modalities）保留，
    新写的模型只给 name —— 剩下的让 OpenCode 自己猜。
    """
    out: dict = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        mid, _, label = line.partition(" ")
        mid = mid.strip()
        if not mid:
            continue
        label = label.strip()
        out[mid] = {"name": label or mid}
    return out


def models_text(p: Provider) -> str:
    """反向：models 结构 -> 一行一个 的可编辑文本。"""
    lines = []
    models = p.models if isinstance(p.models, dict) else {}
    for mid, node in models.items():
        label = ""
        if isinstance(node, dict):
            label = node.get("name") or ""
        lines.append(f"{mid} {label}".rstrip())
    return "\n".join(lines)


class ProviderStore:
    """provider 库。复用主库的连接和锁，避免开第二个连接抢写。

    config_path 显式持有目标配置文件：所有写操作都走这里，
    不留「默认路径」这种隐式写入——测试时传临时文件，
    绝不会误伤用户真实的 opencode.jsonc。
    """

    def __init__(self, store, config_path: Path | str | None = None):
        self.conn: sqlite3.Connection = store.conn
        self._lock = store._lock
        self.config_path = Path(config_path) if config_path else oc.config_path()
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # ------------------------------------------------------------- 读
    def list(self) -> list[Provider]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, name, npm, base_url, api_key_enc, models_json,"
                " default_model, is_current, sort_index"
                " FROM oc_providers ORDER BY sort_index, created_at").fetchall()
        out = []
        for r in rows:
            try:
                models = json.loads(r["models_json"] or "{}")
            except json.JSONDecodeError:
                models = {}
            key = ""
            if r["api_key_enc"]:
                try:
                    key = dpapi.unprotect(r["api_key_enc"])
                except Exception:  # noqa: BLE001
                    key = ""      # 解不开（换账户/entropy 变了），让用户重填
            out.append(Provider(
                id=r["id"], name=r["name"], npm=r["npm"], base_url=r["base_url"],
                api_key=key, models=models if isinstance(models, dict) else {},
                default_model=r["default_model"], is_current=bool(r["is_current"]),
                sort_index=r["sort_index"]))
        return out

    def get(self, pid: str) -> Provider | None:
        for p in self.list():
            if p.id == pid:
                return p
        return None

    def current(self) -> Provider | None:
        for p in self.list():
            if p.is_current:
                return p
        return None

    # ------------------------------------------------------------- 写
    def save(self, p: Provider) -> None:
        now = int(time.time() * 1000)
        with self._lock:
            self.conn.execute(
                "INSERT INTO oc_providers"
                " (id, name, npm, base_url, api_key_enc, models_json,"
                "  default_model, is_current, sort_index, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " name=excluded.name, npm=excluded.npm, base_url=excluded.base_url,"
                " api_key_enc=excluded.api_key_enc, models_json=excluded.models_json,"
                " default_model=excluded.default_model, is_current=excluded.is_current,"
                " sort_index=excluded.sort_index, updated_at=excluded.updated_at",
                (p.id, p.name, p.npm, p.base_url,
                 dpapi.protect(p.api_key) if p.api_key else "",
                 _models_text(p), p.default_model,
                 1 if p.is_current else 0, p.sort_index, now, now))
            self.conn.commit()

    def delete(self, pid: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM oc_providers WHERE id=?", (pid,))
            self.conn.commit()

    def set_current(self, pid: str) -> None:
        with self._lock:
            self.conn.execute("UPDATE oc_providers SET is_current=0")
            self.conn.execute("UPDATE oc_providers SET is_current=1 WHERE id=?", (pid,))
            self.conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM oc_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO oc_meta(key, value) VALUES(?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
            self.conn.commit()

    # ------------------------------------------------------------- 默认模型
    def default_model(self) -> str:
        """全局默认模型，形如 providerId/modelId。"""
        return self.get_meta("default_model", "")

    def set_default_model(self, value: str) -> None:
        self.set_meta("default_model", value or "")

    def model_choices(self) -> list[tuple[str, str, str]]:
        """所有可选项：(providerId, modelId, "providerId/modelId 显示名")。"""
        out = []
        for p in self.list():
            for mid in p.model_ids():
                out.append((p.id, mid,
                            f"{p.id}/{mid}  {oc.model_label(p.to_json(), mid)}"))
        return out

    # ------------------------------------------------------------- 导入
    def import_from_opencode_config(self, path: Path | None = None) -> int:
        """把现有 opencode.jsonc 里的 provider 导进来（不用重敲 key）。"""
        cfg = oc.read(path)
        found = oc.providers_from(cfg)
        if not found:
            return 0
        existing = {p.id: p for p in self.list()}
        n = 0
        for item in found:
            old = existing.get(item["id"])
            key = item["api_key"]
            if old and old.api_key and not key:
                key = old.api_key          # 文件里没写 key 就沿用库里那份
            p = Provider(
                id=item["id"], name=item["name"] or item["id"], npm=item["npm"],
                base_url=item["base_url"], api_key=key, models=item["models"],
                default_model=(old.default_model if old else ""),
                is_current=(old.is_current if old else False),
                sort_index=(old.sort_index if old else len(self.list())))
            if old and old.default_model and old.default_model in p.models:
                p.default_model = old.default_model
            self.save(p)
            n += 1
        self.adopt_global_model(cfg.get("model") or "")
        return n

    def adopt_global_model(self, gmodel: str) -> None:
        """把 opencode.jsonc 里的全局默认模型（"provider/model"）记进库里。

        不记的话，配置界面上「当前生效的 provider」和「全局默认模型」
        永远是空的 —— 看着像配置没生效，其实只是没读进来。
        """
        gmodel = (gmodel or "").strip()
        if not gmodel:
            return
        self.set_default_model(gmodel)
        pid, _, mid = gmodel.partition("/")
        if not pid:
            return
        for p in self.list():
            if p.id != pid:
                continue
            p.is_current = True
            if mid:
                p.default_model = mid
            self.save(p)
            return

    def import_from_ccswitch(self, db_path: Path | None = None) -> int:
        """从 cc-switch.db 里导 ccswitch 已有的 opencode provider。"""
        p = Path(db_path) if db_path else Path.home() / ".cc-switch" / "cc-switch.db"
        if not p.exists():
            raise FileNotFoundError(f"没找到 ccswitch 数据库：{p}")
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT id, name, settings_config FROM providers"
                " WHERE app_type='opencode'").fetchall()
        finally:
            con.close()
        existing = {x.id: x for x in self.list()}
        n = 0
        for r in rows:
            try:
                cfg = json.loads(r["settings_config"] or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(cfg, dict):
                continue
            opts = cfg.get("options") or {}
            models = cfg.get("models") or {}
            pid = r["id"]
            old = existing.get(pid)
            key = opts.get("apiKey") or ""
            if old and old.api_key and not key:
                key = old.api_key
            prov = Provider(
                id=pid, name=r["name"] or cfg.get("name") or pid,
                npm=cfg.get("npm") or oc.DEFAULT_NPM,
                base_url=opts.get("baseURL") or "", api_key=key,
                models=models if isinstance(models, dict) else {},
                default_model=(old.default_model if old else ""),
                is_current=(old.is_current if old else False),
                sort_index=(old.sort_index if old else len(self.list())))
            self.save(prov)
            n += 1
        return n

    # ------------------------------------------------------------- 投影
    def export_to_opencode_config(self, path: Path | None = None) -> Path:
        """把库里的 provider 全量写回 opencode.jsonc，并设置默认模型。"""
        p = Path(path) if path else self.config_path
        cfg = oc.read(p)
        providers = [x.to_json() for x in self.list()]
        new_cfg = oc.apply_providers(cfg, providers, self.default_model())
        return oc.write(new_cfg, p)

    def apply_model(self, pid: str, mid: str) -> str:
        """把 providerId/modelId 设为默认模型并落盘。"""
        value = f"{pid}/{mid}"
        self.set_default_model(value)
        self.export_to_opencode_config()
        return value

    def switch_to(self, pid: str, mid: str = "") -> str:
        """切到某个 provider（并可选指定模型），落盘。"""
        p = self.get(pid)
        if p is None:
            raise KeyError(f"没有这个 provider：{pid}")
        self.set_current(pid)
        if mid:
            p.default_model = mid
            p.is_current = True
            self.save(p)
            self.set_default_model(f"{pid}/{mid}")
        elif p.default_model:
            self.set_default_model(f"{pid}/{p.default_model}")
        self.export_to_opencode_config()
        return self.default_model()
