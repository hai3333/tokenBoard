"""SQLite 存储：用量事件表 + 同步水位表。

设计参考 CC Switch：
  - usage_events      请求级明细，唯一键 (app, request_id) 保证幂等重扫
  - sync_state        每个源文件的扫描水位（mtime / size / rowid），实现增量扫描
  - model_pricing     价格表

线程模型：UI 在主线程读，扫描在后台线程写。
连接用 check_same_thread=False + 可重入锁串行化所有访问。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, Iterator

from .models import UsageRecord

# 云同步导出用的列顺序（和 SCHEMA 一一对应，改表时两边一起改）
USAGE_COLS = (
    "app", "source", "request_id", "ts_ms", "day", "model",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
    "reasoning_tokens", "total_tokens", "cost_usd", "session_id", "project",
)
SPEED_COLS = (
    "app", "source", "sample_id", "ts_ms", "day", "model", "kind",
    "ttft_ms", "duration_ms", "output_tokens",
)


def model_key(raw: str) -> str:
    """模型归一化键：去掉厂商前缀 + 小写。"""
    return (raw or "").split("/")[-1].strip().lower()


def model_display(raw: str) -> str:
    """展示名：去掉厂商前缀，保留原大小写。"""
    return (raw or "").split("/")[-1].strip()


def _pct(sorted_vals: list[int], q: float) -> float:
    """有序列表的分位数（线性插值）。空列表返回 0。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return float(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac)

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    app               TEXT NOT NULL,
    source            TEXT NOT NULL,
    request_id        TEXT NOT NULL,
    ts_ms             INTEGER NOT NULL,
    day               TEXT NOT NULL,
    model             TEXT NOT NULL DEFAULT '',
    input_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL NOT NULL DEFAULT 0,
    session_id        TEXT NOT NULL DEFAULT '',
    project           TEXT NOT NULL DEFAULT '',
    UNIQUE(app, request_id)
);

CREATE INDEX IF NOT EXISTS idx_usage_day   ON usage_events(day);
CREATE INDEX IF NOT EXISTS idx_usage_app   ON usage_events(app);
CREATE INDEX IF NOT EXISTS idx_usage_ts    ON usage_events(ts_ms);

CREATE TABLE IF NOT EXISTS sync_state (
    app          TEXT NOT NULL,
    locator      TEXT NOT NULL,
    mtime        REAL NOT NULL DEFAULT 0,
    size         INTEGER NOT NULL DEFAULT 0,
    watermark    INTEGER NOT NULL DEFAULT 0,
    last_synced  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (app, locator)
);

CREATE TABLE IF NOT EXISTS model_pricing (
    model_id            TEXT PRIMARY KEY,
    display_name        TEXT NOT NULL DEFAULT '',
    input_per_million  REAL NOT NULL DEFAULT 0,
    output_per_million REAL NOT NULL DEFAULT 0,
    cache_read_per_million  REAL NOT NULL DEFAULT 0,
    cache_write_per_million REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 速度采样：首字耗时（ttft_ms）/ 端到端耗时（duration_ms）。
-- 和用量分开存：粒度不同（有的源只到「轮」级），聚合口径也不一样。
CREATE TABLE IF NOT EXISTS speed_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    app           TEXT NOT NULL,
    source        TEXT NOT NULL,
    sample_id     TEXT NOT NULL,
    ts_ms         INTEGER NOT NULL,
    day           TEXT NOT NULL,
    model         TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL DEFAULT 'call',
    ttft_ms       INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    UNIQUE(app, sample_id)
);

CREATE INDEX IF NOT EXISTS idx_speed_day ON speed_samples(day);
"""


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # ------------------------------------------------------------- 用量写入
    def upsert_usage(self, records: Iterable[UsageRecord]) -> int:
        rows = [
            (
                r.app, r.source, r.request_id, r.ts_ms, r.day, r.model,
                r.input_tokens, r.output_tokens, r.cache_read_tokens,
                r.cache_write_tokens, r.reasoning_tokens, r.total_tokens,
                r.cost_usd, r.session_id, r.project,
            )
            for r in records
        ]
        if not rows:
            return 0
        with self._lock:
            before = self.conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO usage_events
                    (app, source, request_id, ts_ms, day, model, input_tokens,
                     output_tokens, cache_read_tokens, cache_write_tokens,
                     reasoning_tokens, total_tokens, cost_usd, session_id, project)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )
            self.conn.commit()
            after = self.conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        return max(0, after - before)

    def count_usage(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]

    def clear_sync(self) -> None:
        """清空扫描水位，下次扫描按全量重读（新增字段回填用）。"""
        with self._lock:
            self.conn.execute("DELETE FROM sync_state")
            self.conn.commit()

    def count_speed(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM speed_samples").fetchone()[0]

    # ------------------------------------------------------------- 速度采样
    def upsert_speed(self, samples: Iterable) -> int:
        """写入速度采样。

        允许覆盖：OpenCode 的「首字」要等分片写完之后才算得出来，
        同一 message 前面几轮可能先落了个 0，后面再补上真实值。
        """
        rows = [
            (
                s.app, s.source, s.sample_id, s.ts_ms, s.day, s.model,
                s.kind, int(s.ttft_ms or 0), int(s.duration_ms or 0),
                int(s.output_tokens or 0),
            )
            for s in samples
        ]
        if not rows:
            return 0
        with self._lock:
            before = self.conn.total_changes
            self.conn.executemany(
                """
                INSERT INTO speed_samples
                    (app, source, sample_id, ts_ms, day, model, kind,
                     ttft_ms, duration_ms, output_tokens)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(app, sample_id) DO UPDATE SET
                    ts_ms=excluded.ts_ms, day=excluded.day, model=excluded.model,
                    kind=excluded.kind,
                    ttft_ms=MAX(speed_samples.ttft_ms, excluded.ttft_ms),
                    duration_ms=MAX(speed_samples.duration_ms, excluded.duration_ms),
                    output_tokens=MAX(speed_samples.output_tokens, excluded.output_tokens)
                """,
                rows,
            )
            self.conn.commit()
            return self.conn.total_changes - before

    def speed_stats(self, since_day: str | None = None) -> dict:
        """速度聚合：按 app、按模型、按 (app, 模型) 三个维度。

        返回 {"apps": {...}, "models": {...}, "pairs": {(app, key): ...},
              "total": {...}}
        每个 stats：
            n         采样数
            n_ttft    有首字数据的采样数
            ttft_p50  首字中位数（ms）
            ttft_p90  首字 P90（ms）
            n_call    「单次调用」级采样数（算耗时/速度只用这些，
                      轮级耗时里混着工具执行时间，会把速度算低）
            dur_avg   单次调用的平均耗时（ms）
            tps       输出吞吐 = 输出 token 总数 / 耗时总秒数
            out       输出 token 合计
        """
        sql = ["SELECT app, model, kind, ttft_ms, duration_ms, output_tokens",
               "FROM speed_samples WHERE 1=1"]
        params: list = []
        if since_day:
            sql.append("AND day >= ?")
            params.append(since_day)
        with self._lock:
            rows = [dict(r) for r in self.conn.execute(" ".join(sql), params)]

        apps: dict[str, dict] = {}
        models: dict[str, dict] = {}
        pairs: dict[tuple, dict] = {}
        total = {"ttft": [], "dur": 0, "out": 0, "n": 0, "n_call": 0,
                 "n_ttft": 0}

        def bucket(store: dict, key) -> dict:
            b = store.get(key)
            if b is None:
                b = store[key] = {"ttft": [], "dur": 0, "out": 0, "n": 0,
                                  "n_call": 0, "n_ttft": 0}
            return b

        for r in rows:
            key = model_key(r["model"]) if r["model"] else ""
            targets = [total, bucket(apps, r["app"])]
            if key:
                targets.append(bucket(models, key))
                targets.append(bucket(pairs, (r["app"], key)))
            for b in targets:
                b["n"] += 1
                if r["ttft_ms"] and r["ttft_ms"] > 0:
                    b["ttft"].append(int(r["ttft_ms"]))
                    b["n_ttft"] += 1
                if r["kind"] == "call" and (r["duration_ms"] or 0) > 0:
                    b["n_call"] += 1
                    b["dur"] += int(r["duration_ms"])
                    b["out"] += int(r["output_tokens"] or 0)

        def finish(b: dict) -> dict:
            ttft = sorted(b["ttft"])
            dur = b["dur"]
            return {
                "n": b["n"],
                "n_ttft": b["n_ttft"],
                "ttft_p50": _pct(ttft, 0.50),
                "ttft_p90": _pct(ttft, 0.90),
                "n_call": b["n_call"],
                "dur_avg": (dur / b["n_call"]) if b["n_call"] else 0.0,
                "tps": (b["out"] / (dur / 1000.0)) if dur > 0 else 0.0,
                "out": b["out"],
            }

        return {
            "apps": {k: finish(v) for k, v in apps.items()},
            "models": {k: finish(v) for k, v in models.items()},
            "pairs": {k: finish(v) for k, v in pairs.items()},
            "total": finish(total),
        }

    # ------------------------------------------------------------- 同步水位
    def get_sync(self, app: str, locator: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM sync_state WHERE app=? AND locator=?", (app, locator)
            ).fetchone()

    def set_sync(self, app: str, locator: str, mtime: float, size: int,
                 watermark: int) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO sync_state (app, locator, mtime, size, watermark, last_synced)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(app, locator) DO UPDATE SET
                    mtime=excluded.mtime, size=excluded.size,
                    watermark=excluded.watermark, last_synced=excluded.last_synced
                """,
                (app, locator, mtime, size, watermark, int(time.time())),
            )
            self.conn.commit()

    def watermark(self, app: str, locator: str) -> int:
        row = self.get_sync(app, locator)
        return int(row["watermark"]) if row else 0

    # ------------------------------------------------------------- 价格表
    def load_pricing(self, payload: dict) -> int:
        rows = [
            (
                model_id,
                p.get("display_name", model_id),
                float(p.get("input", 0)),
                float(p.get("output", 0)),
                float(p.get("cache_read", 0)),
                float(p.get("cache_write", 0)),
            )
            for model_id, p in payload.items()
        ]
        if not rows:
            return 0
        with self._lock:
            self.conn.executemany(
                """
                INSERT INTO model_pricing
                    (model_id, display_name, input_per_million, output_per_million,
                     cache_read_per_million, cache_write_per_million)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(model_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    input_per_million=excluded.input_per_million,
                    output_per_million=excluded.output_per_million,
                    cache_read_per_million=excluded.cache_read_per_million,
                    cache_write_per_million=excluded.cache_write_per_million
                """,
                rows,
            )
            self.conn.commit()
        return len(rows)

    def pricing_map(self) -> dict[str, dict]:
        with self._lock:
            return {
                r["model_id"]: {
                    "input": r["input_per_million"],
                    "output": r["output_per_million"],
                    "cache_read": r["cache_read_per_million"],
                    "cache_write": r["cache_write_per_million"],
                }
                for r in self.conn.execute("SELECT * FROM model_pricing")
            }

    # ------------------------------------------------------------- 设置
    def set_meta(self, key: str, value) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self.conn.commit()

    def get_meta(self, key: str, default=None):
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:  # noqa: BLE001
            return default

    # ------------------------------------------------------------- 查询
    def summary(self, since_day: str | None = None,
                until_day: str | None = None) -> list[dict]:
        sql = [
            "SELECT app,",
            "  COUNT(*)             AS requests,",
            "  SUM(input_tokens)      AS input_tokens,",
            "  SUM(output_tokens)     AS output_tokens,",
            "  SUM(cache_read_tokens) AS cache_read_tokens,",
            "  SUM(cache_write_tokens)AS cache_write_tokens,",
            "  SUM(reasoning_tokens)  AS reasoning_tokens,",
            "  SUM(total_tokens)      AS total_tokens,",
            "  SUM(cost_usd)          AS cost_usd,",
            "  MAX(ts_ms)             AS last_ts",
            "FROM usage_events WHERE 1=1",
        ]
        params: list = []
        if since_day:
            sql.append("AND day >= ?")
            params.append(since_day)
        if until_day:
            sql.append("AND day <= ?")
            params.append(until_day)
        sql.append("GROUP BY app ORDER BY total_tokens DESC")
        with self._lock:
            return [dict(r) for r in self.conn.execute(" ".join(sql), params)]

    def summary_by_model(self, since_day: str | None = None, app: str | None = None,
                         limit: int = 50) -> list[dict]:
        sql = [
            "SELECT app, model,",
            "  COUNT(*)          AS requests,",
            "  SUM(total_tokens) AS total_tokens,",
            "  SUM(cost_usd)     AS cost_usd",
            "FROM usage_events WHERE total_tokens > 0",
        ]
        params: list = []
        if since_day:
            sql.append("AND day >= ?")
            params.append(since_day)
        if app:
            sql.append("AND app = ?")
            params.append(app)
        sql.append("GROUP BY app, model ORDER BY total_tokens DESC LIMIT ?")
        params.append(limit)
        with self._lock:
            return [dict(r) for r in self.conn.execute(" ".join(sql), params)]

    def models_by_app(self, since_day: str | None = None) -> dict[str, list[dict]]:
        """app -> 该应用下各模型的用量（同名模型已合并）。"""
        rows = self.summary_by_model(since_day=since_day, limit=100000)
        out: dict[str, dict[str, dict]] = {}
        for r in rows:
            key = model_key(r["model"])
            app = r["app"]
            g = out.setdefault(app, {}).setdefault(key, {
                "key": key,
                "name": model_display(r["model"]),
                "tokens": 0, "requests": 0, "cost": 0.0, "models": set(),
            })
            g["tokens"] += r["total_tokens"] or 0
            g["requests"] += r["requests"] or 0
            g["cost"] += r["cost_usd"] or 0.0
            g["models"].add(r["model"])
        result: dict[str, list[dict]] = {}
        for app, groups in out.items():
            lst = [{
                "key": g["key"],
                "name": g["name"],
                "tokens": g["tokens"],
                "requests": g["requests"],
                "cost": g["cost"],
                "aliases": len(g["models"]),
            } for g in groups.values()]
            lst.sort(key=lambda x: -x["tokens"])
            result[app] = lst
        return result

    def apps_by_model(self, since_day: str | None = None) -> dict[str, list[dict]]:
        """模型 key -> 各工具的用量（这个模型在哪些工具里用过）。"""
        rows = self.summary_by_model(since_day=since_day, limit=100000)
        out: dict[str, dict[str, dict]] = {}
        for r in rows:
            key = model_key(r["model"])
            app = r["app"]
            g = out.setdefault(key, {}).setdefault(app, {
                "app": app,
                "name": model_display(r["model"]),
                "tokens": 0, "requests": 0, "cost": 0.0,
            })
            g["tokens"] += r["total_tokens"] or 0
            g["requests"] += r["requests"] or 0
            g["cost"] += r["cost_usd"] or 0.0
        result: dict[str, list[dict]] = {}
        for key, groups in out.items():
            lst = list(groups.values())
            lst.sort(key=lambda x: -x["tokens"])
            result[key] = lst
        return result

    def models_aggregated(self, since_day: str | None = None,
                          limit: int = 500) -> list[dict]:
        """按模型汇总（跨应用合并同名模型）。

        同一个模型在不同工具里写法可能不一样：
            hs/deepseek-v4.1-flash / bailian/deepseek-v4.1-flash / deepseek-v4.1-flash
        统一去掉厂商前缀后再合并，展示时取最常见的写法。
        """
        sql = [
            "SELECT model, app,",
            "  COUNT(*)          AS requests,",
            "  SUM(total_tokens) AS total_tokens,",
            "  SUM(input_tokens) AS input_tokens,",
            "  SUM(output_tokens) AS output_tokens,",
            "  SUM(cache_read_tokens) AS cache_read_tokens,",
            "  SUM(cost_usd)     AS cost_usd",
            "FROM usage_events WHERE model <> '' AND total_tokens > 0",
        ]
        params: list = []
        # 过滤条件必须加在 GROUP BY 之前，
        # 追加到后面会被 SQLite 当成 GROUP BY 表达式的一部分，筛选直接失效。
        if since_day:
            sql.append("AND day >= ?")
            params.append(since_day)
        sql.append("GROUP BY model, app")
        with self._lock:
            rows = [dict(r) for r in self.conn.execute(" ".join(sql), params)]

        groups: dict[str, dict] = {}
        for r in rows:
            raw = r["model"]
            key = model_key(raw)
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    "key": key,
                    "name": model_display(raw),
                    "requests": 0, "total_tokens": 0, "input_tokens": 0,
                    "output_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0,
                    "_spell": {}, "_raw": {}, "_app": {},
                }
            g["requests"] += r["requests"]
            g["total_tokens"] += r["total_tokens"] or 0
            g["input_tokens"] += r["input_tokens"] or 0
            g["output_tokens"] += r["output_tokens"] or 0
            g["cache_read_tokens"] += r["cache_read_tokens"] or 0
            g["cost_usd"] += r["cost_usd"] or 0
            g["_spell"][raw] = g["_spell"].get(raw, 0) + (r["requests"] or 0)
            g["_raw"][raw] = g["_raw"].get(raw, 0) + (r["total_tokens"] or 0)
            g["_app"][r["app"]] = g["_app"].get(r["app"], 0) + (r["total_tokens"] or 0)

        out = []
        for g in groups.values():
            # 展示名取 token 量最大的那种写法
            best = max(g["_raw"].items(), key=lambda kv: kv[1])[0]
            g["name"] = model_display(best)
            g["aliases"] = sorted(g["_raw"].keys(), key=lambda k: -g["_raw"][k])
            # 主要贡献者（决定条形图配色）
            g["app"] = max(g["_app"].items(), key=lambda kv: kv[1])[0]
            g.pop("_spell")
            g.pop("_raw")
            g.pop("_app")
            out.append(g)
        out.sort(key=lambda g: -g["total_tokens"])
        return out[:limit]

    def daily(self, since_day: str | None = None, app: str | None = None) -> list[dict]:
        sql = ["SELECT day, app, SUM(total_tokens) AS total_tokens, SUM(cost_usd) AS cost_usd",
               "FROM usage_events WHERE 1=1"]
        params: list = []
        if since_day:
            sql.append("AND day >= ?")
            params.append(since_day)
        if app:
            sql.append("AND app = ?")
            params.append(app)
        sql.append("GROUP BY day, app ORDER BY day ASC")
        with self._lock:
            return [dict(r) for r in self.conn.execute(" ".join(sql), params)]

    def recent(self, limit: int = 50, app: str | None = None) -> list[dict]:
        sql = ["SELECT app, model, day, total_tokens, cost_usd, ts_ms, session_id, project",
               "FROM usage_events WHERE 1=1"]
        params: list = []
        if app:
            sql.append("AND app = ?")
            params.append(app)
        sql.append("ORDER BY ts_ms DESC LIMIT ?")
        params.append(limit)
        with self._lock:
            return [dict(r) for r in self.conn.execute(" ".join(sql), params)]

    def prune_older_than(self, keep_days: int = 400) -> int:
        cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - keep_days * 86400))
        with self._lock:
            cur = self.conn.execute("DELETE FROM usage_events WHERE day < ?", (cutoff,))
            self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------- 云同步
    def open_reader(self) -> sqlite3.Connection:
        """开一个只读连接，专门给导出快照用。

        为什么要另开一个：导出可能扫几十万行，占着主连接的锁会把界面
        卡成幻灯片。WAL 模式下读连接和写连接互不阻塞，代价只是多一个句柄。
        """
        conn = sqlite3.connect(str(self.path), timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def iter_usage_rows(conn: sqlite3.Connection) -> Iterator[tuple]:
        """按插入顺序导出用量行（列顺序 = USAGE_COLS）。"""
        cur = conn.execute(
            f"SELECT {', '.join(USAGE_COLS)} FROM usage_events ORDER BY id")
        for r in cur:
            yield tuple(r)

    @staticmethod
    def iter_speed_rows(conn: sqlite3.Connection) -> Iterator[tuple]:
        """按插入顺序导出速度采样行（列顺序 = SPEED_COLS）。"""
        cur = conn.execute(
            f"SELECT {', '.join(SPEED_COLS)} FROM speed_samples ORDER BY id")
        for r in cur:
            yield tuple(r)

    def import_usage_rows(self, rows: list[tuple]) -> int:
        """并入远端用量行：唯一键冲突的忽略，返回真正新增的条数。"""
        if not rows:
            return 0
        with self._lock:
            before = self.conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
            self.conn.executemany(
                f"INSERT OR IGNORE INTO usage_events ({', '.join(USAGE_COLS)}) "
                f"VALUES ({','.join('?' * len(USAGE_COLS))})",
                rows,
            )
            self.conn.commit()
            after = self.conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        return max(0, after - before)

    def import_speed_rows(self, rows: list[tuple]) -> int:
        """并入远端速度采样：和本地写入同一套「取较大值」规则。"""
        if not rows:
            return 0
        with self._lock:
            before = self.conn.total_changes
            self.conn.executemany(
                f"""
                INSERT INTO speed_samples ({', '.join(SPEED_COLS)})
                VALUES ({','.join('?' * len(SPEED_COLS))})
                ON CONFLICT(app, sample_id) DO UPDATE SET
                    ts_ms=excluded.ts_ms, day=excluded.day, model=excluded.model,
                    kind=excluded.kind,
                    ttft_ms=MAX(speed_samples.ttft_ms, excluded.ttft_ms),
                    duration_ms=MAX(speed_samples.duration_ms, excluded.duration_ms),
                    output_tokens=MAX(speed_samples.output_tokens, excluded.output_tokens)
                """,
                rows,
            )
            self.conn.commit()
            return self.conn.total_changes - before

    def data_fingerprint(self) -> dict:
        """数据指纹：用来判断「本地有没有新东西要传」。

        只比行数和最大 id —— 比整库哈希便宜得多，也够用了：
        库只增不删，行数或 max(id) 变了就说明有新记录。
        """
        with self._lock:
            u = self.conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(MAX(id),0) AS mx FROM usage_events"
            ).fetchone()
            s = self.conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(MAX(id),0) AS mx FROM speed_samples"
            ).fetchone()
        return {
            "usage": [int(u["n"]), int(u["mx"])],
            "speed": [int(s["n"]), int(s["mx"])],
        }

    def counts(self) -> tuple[int, int]:
        """(用量条数, 速度采样条数)，界面显示用。"""
        with self._lock:
            u = self.conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
            s = self.conn.execute("SELECT COUNT(*) FROM speed_samples").fetchone()[0]
        return int(u), int(s)

    def close(self) -> None:
        try:
            with self._lock:
                self.conn.close()
        except Exception:  # noqa: BLE001
            pass
