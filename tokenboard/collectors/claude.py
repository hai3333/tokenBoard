"""Claude Code 采集器：~/.claude/projects/**/*.jsonl

记录结构：
    {"type":"assistant","requestId":"...","uuid":"...","timestamp":"...",
     "message":{"id":"msg_...","model":"...","usage":{...}},"cwd":"..."}
usage 字段：input_tokens / output_tokens / cache_creation_input_tokens / cache_read_input_tokens
"""
from __future__ import annotations

from datetime import datetime

from ..config import CLAUDE_DIR
from ..models import UsageRecord
from .base import BaseCollector, file_stat, iter_jsonl


def parse_ts(value) -> int:
    """ISO8601 -> epoch ms"""
    if isinstance(value, (int, float)):
        return int(value if value > 1e11 else value * 1000)
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return 0


class ClaudeCollector(BaseCollector):
    app = "claude"
    source = "claude_session_log"

    def available(self) -> bool:
        return CLAUDE_DIR.is_dir()

    def collect(self) -> list[UsageRecord]:
        best: dict[str, UsageRecord] = {}
        if not CLAUDE_DIR.is_dir():
            return []

        for path in sorted(CLAUDE_DIR.rglob("*.jsonl")):
            try:
                mtime, size = file_stat(str(path))
            except OSError:
                continue
            locator = str(path)
            if not self._file_changed(locator, locator, mtime, size):
                continue

            for obj in iter_jsonl(str(path)):
                rec = self._parse(obj)
                if rec is None:
                    continue
                # 同一个 message 可能被多次写入（流式/更新），保留 token 最大的一条
                prev = best.get(rec.request_id)
                if prev is None or rec.total_tokens > prev.total_tokens:
                    best[rec.request_id] = rec

            self._mark_synced(locator, locator, mtime, size)

        return list(best.values())

    # ------------------------------------------------------------------
    def _parse(self, obj: dict) -> UsageRecord | None:
        if obj.get("type") != "assistant":
            return None
        message = obj.get("message")
        if not isinstance(message, dict):
            return None
        usage = message.get("usage")
        if not isinstance(usage, dict):
            return None

        inp = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        cr = int(usage.get("cache_read_input_tokens") or 0)
        cw = int(usage.get("cache_creation_input_tokens") or 0)
        if inp + out + cr + cw == 0:
            return None

        rid = (obj.get("requestId") or message.get("id") or obj.get("uuid") or "")
        if not rid:
            rid = f"{obj.get('sessionId','')}-{obj.get('uuid','')}"

        return UsageRecord(
            app=self.app,
            source=self.source,
            request_id=str(rid),
            ts_ms=parse_ts(obj.get("timestamp")) or parse_ts(message.get("timestamp")),
            model=str(message.get("model") or ""),
            input_tokens=inp,
            output_tokens=out,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
            session_id=str(obj.get("sessionId") or ""),
            project=str(obj.get("cwd") or ""),
        )
