"""OpenCode 采集器：~/.local/share/opencode/opencode.db

表 message 的 data 列是 JSON，assistant 消息里带 tokens：
    {"role":"assistant", "modelID":"gpt-5.3-codex", "providerID":"openai",
     "tokens":{"total":9834,"input":9544,"output":37,"reasoning":253,
               "cache":{"write":0,"read":0}},
     "cost":0, "time":{"created":...}}

增量：按隐式 rowid 水位读取（比按时间戳稳，避免同毫秒漏记）。
"""
from __future__ import annotations

import json
import sqlite3

from ..config import OPENCODE_DB
from ..models import UsageRecord
from .base import BaseCollector, file_stat

LOCATOR = "message"


class OpenCodeCollector(BaseCollector):
    app = "opencode"
    source = "opencode_session"

    def available(self) -> bool:
        return OPENCODE_DB.exists()

    def collect(self) -> list[UsageRecord]:
        self.samples = []
        if not OPENCODE_DB.exists():
            return []

        mtime, size = file_stat(str(OPENCODE_DB))
        watermark = self.store.watermark(self.app, LOCATOR)

        try:
            conn = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True, timeout=15)
            # opencode.db 有 300MB+，关掉 mmap 并压小页缓存，避免把文件映射进内存
            conn.execute("PRAGMA mmap_size=0")
            conn.execute("PRAGMA cache_size=-2000")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT rowid AS rid, id, session_id, time_created, time_updated, data
                FROM message
                WHERE rowid > ?
                ORDER BY rowid
                """,
                (watermark,),
            ).fetchall()
            self._collect_speed(conn)
            conn.close()
        except sqlite3.Error as e:
            raise RuntimeError(f"读取 OpenCode 数据库失败: {e}") from e

        out: list[UsageRecord] = []
        max_rid = watermark
        for r in rows:
            rid = int(r["rid"])
            max_rid = max(max_rid, rid)
            try:
                d = json.loads(r["data"])
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(d, dict) or d.get("role") != "assistant":
                continue
            tokens = d.get("tokens")
            if not isinstance(tokens, dict):
                continue

            inp = int(tokens.get("input") or 0)
            out_tok = int(tokens.get("output") or 0)
            reasoning = int(tokens.get("reasoning") or 0)
            cache = tokens.get("cache") or {}
            cr = int(cache.get("read") or 0)
            cw = int(cache.get("write") or 0)
            if inp + out_tok + cr + cw == 0:
                continue

            ts = int(d.get("time", {}).get("completed")
                     or r["time_created"] or 0)
            model = str(d.get("modelID") or "")
            provider = str(d.get("providerID") or "")
            full_model = f"{provider}/{model}" if provider and model else model

            out.append(UsageRecord(
                app=self.app,
                source=self.source,
                request_id=str(r["id"]),
                ts_ms=ts,
                model=full_model,
                input_tokens=inp,
                output_tokens=out_tok,
                cache_read_tokens=cr,
                cache_write_tokens=cw,
                reasoning_tokens=reasoning,
                cost_usd=float(d.get("cost") or 0.0),
                session_id=str(r["session_id"] or ""),
                project=str(d.get("path", {}).get("cwd") or ""),
            ))

        self._mark_synced(LOCATOR, str(OPENCODE_DB), mtime, size, max_rid)
        return out

    # ------------------------------------------------------------------
    def _collect_speed(self, conn) -> None:
        """首字 = 第一个分片落盘 - 消息创建；耗时 = 消息完成 - 创建。

        part 是流式分片，消息刚创建时还没有分片，所以每次扫描都回看最近
        800 条消息重算一遍（库里是 upsert 覆盖），否则先落成 0 的永远补不上。
        """
        try:
            rows = conn.execute(
                """
                SELECT m.id, m.time_created, m.data,
                       MIN(CAST(p.time_created AS INTEGER)) AS first_part,
                       MAX(CAST(p.time_updated AS INTEGER)) AS last_part
                FROM message m
                LEFT JOIN part p ON p.message_id = m.id
                WHERE m.rowid > (SELECT COALESCE(MAX(rowid), 0) FROM message) - 800
                  AND m.data LIKE '%"role":"assistant"%'
                GROUP BY m.id
                """
            ).fetchall()
        except sqlite3.Error:
            return

        for r in rows:
            try:
                d = json.loads(r["data"])
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(d, dict):
                continue
            created = int(r["time_created"] or 0)
            if not created:
                continue
            tokens = d.get("tokens") or {}
            out_tok = int(tokens.get("output") or 0)
            completed = int((d.get("time") or {}).get("completed") or 0)
            if not completed:
                completed = int(r["last_part"] or 0)
            first = int(r["first_part"] or 0)

            dur = max(0, completed - created) if completed else 0
            ttft = max(0, first - created) if first and dur else 0
            model = str(d.get("modelID") or "")
            provider = str(d.get("providerID") or "")
            full_model = f"{provider}/{model}" if provider and model else model
            self._sample(f"msg:{r['id']}", completed or created, full_model,
                         kind="call", ttft_ms=ttft, duration_ms=dur,
                         output_tokens=out_tok)
