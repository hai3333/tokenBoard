"""MiniMax Code 采集器：~/.minimax/v2/sqlite/runtime-state.sqlite

表 local_runtime_token_usage 已经有请求级用量：
    id, session_id, agent_name, framework_type, turn_id, model, ts,
    input_tokens, output_tokens, reasoning_tokens,
    cache_read_tokens, cache_write_tokens, cost_usd

两个坑：
  1. model 列是 NULL，模型名在 local_runtime_sessions.extra_data_json.effectiveModel
     （形如 "minimax/MiniMax-M3.1-Flash-Preview"），需要按 session_id 关联。
  2. 该库里的 cost_usd 恒为 0，费用要靠价格表自己算。
增量：按自增 id 水位读取。
"""
from __future__ import annotations

import json
import sqlite3

from ..config import MCODEDB
from ..models import UsageRecord
from .base import BaseCollector, file_stat

LOCATOR = "local_runtime_token_usage"


class MCodeCollector(BaseCollector):
    app = "mcode"
    source = "mcode_session"

    def available(self) -> bool:
        return MCODEDB.exists()

    def collect(self) -> list[UsageRecord]:
        if not MCODEDB.exists():
            return []

        mtime, size = file_stat(str(MCODEDB))
        watermark = self.store.watermark(self.app, LOCATOR)

        try:
            conn = sqlite3.connect(f"file:{MCODEDB}?mode=ro", uri=True, timeout=10)
            conn.execute("PRAGMA mmap_size=0")
            conn.execute("PRAGMA cache_size=-2000")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, session_id, agent_name, framework_type, turn_id, model, ts,
                       input_tokens, output_tokens, reasoning_tokens,
                       cache_read_tokens, cache_write_tokens, cost_usd
                FROM local_runtime_token_usage
                WHERE id > ?
                ORDER BY id
                """,
                (watermark,),
            ).fetchall()
            model_map = self._session_models(conn)
            conn.close()
        except sqlite3.Error as e:
            raise RuntimeError(f"读取 MiniMax Code 数据库失败: {e}") from e

        out: list[UsageRecord] = []
        max_id = watermark
        for r in rows:
            rid = int(r["id"])
            max_id = max(max_id, rid)
            inp = int(r["input_tokens"] or 0)
            out_tok = int(r["output_tokens"] or 0)
            cr = int(r["cache_read_tokens"] or 0)
            cw = int(r["cache_write_tokens"] or 0)
            if inp + out_tok + cr + cw == 0:
                continue
            session_id = str(r["session_id"] or "")
            out.append(UsageRecord(
                app=self.app,
                source=self.source,
                request_id=f"mcode-{rid}",
                ts_ms=int(r["ts"] or 0),
                model=str(r["model"] or model_map.get(session_id, "")),
                input_tokens=inp,
                output_tokens=out_tok,
                cache_read_tokens=cr,
                cache_write_tokens=cw,
                reasoning_tokens=int(r["reasoning_tokens"] or 0),
                cost_usd=float(r["cost_usd"] or 0.0),
                session_id=session_id,
                project=str(r["agent_name"] or ""),
            ))

        self._mark_synced(LOCATOR, str(MCODEDB), mtime, size, max_id)
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _session_models(conn) -> dict[str, str]:
        """session_id -> 模型名（来自 extra_data_json.effectiveModel）。"""
        models: dict[str, str] = {}
        try:
            rows = conn.execute(
                "SELECT session_id, extra_data_json FROM local_runtime_sessions "
                "WHERE extra_data_json IS NOT NULL AND extra_data_json LIKE '%effectiveModel%'"
            ).fetchall()
        except sqlite3.Error:
            return models
        for r in rows:
            try:
                data = json.loads(r["extra_data_json"])
            except Exception:  # noqa: BLE001
                continue
            model = data.get("effectiveModel")
            if isinstance(model, str) and model:
                models[str(r["session_id"])] = model
        return models
