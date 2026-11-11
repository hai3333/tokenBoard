"""ZCode 采集器：~/.zcode/cli/rollout/model-io-*.jsonl

CC Switch 看不到 ZCode —— 这是本插件新增的采集源。

每行是一次模型调用的完整 IO 记录：
    {"type":..., "requestId":..., "sessionId":..., "model":{"modelId":...},
     "request":{...}, "response":{"usage":{...}, "providerMetadata":{...}}}

usage 字段（response.usage）：inputTokens / outputTokens / totalTokens /
                              cacheReadTokens / cacheWriteTokens
另有一份上游原始口径 response.providerMetadata.anthropic.usage（snake_case），
cache 读数更全，两边取较大值以免漏计缓存。
"""
from __future__ import annotations

from datetime import datetime

from ..config import ZCODE_DIR
from ..models import UsageRecord
from .base import BaseCollector, file_stat, iter_jsonl


def parse_ts(value) -> int:
    if isinstance(value, (int, float)):
        return int(value if value > 1e11 else value * 1000)
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return 0


class ZCodeCollector(BaseCollector):
    app = "zcode"
    source = "zcode_session"

    def available(self) -> bool:
        return ZCODE_DIR.is_dir()

    def collect(self) -> list[UsageRecord]:
        out: list[UsageRecord] = []
        self.samples = []
        if not ZCODE_DIR.is_dir():
            return []

        for path in sorted(ZCODE_DIR.glob("model-io-*.jsonl")):
            locator = str(path)
            try:
                mtime, size = file_stat(locator)
            except OSError:
                continue
            if not self._file_changed(locator, locator, mtime, size):
                continue

            for obj in iter_jsonl(locator):
                rec = self._parse(obj)
                if rec:
                    out.append(rec)

            self._mark_synced(locator, locator, mtime, size)

        return out

    # ------------------------------------------------------------------
    def _parse(self, obj: dict) -> UsageRecord | None:
        response = obj.get("response")
        if not isinstance(response, dict):
            return None
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return None

        inp = int(usage.get("inputTokens") or 0)
        out = int(usage.get("outputTokens") or 0)
        cr = int(usage.get("cacheReadTokens") or 0)
        cw = int(usage.get("cacheWriteTokens") or 0)

        # 上游原始口径（Anthropic 风格），cache 读数通常更完整
        pm = response.get("providerMetadata")
        if isinstance(pm, dict):
            for prov in pm.values():
                if not isinstance(prov, dict):
                    continue
                raw = prov.get("usage")
                if not isinstance(raw, dict):
                    continue
                inp = max(inp, int(raw.get("input_tokens") or 0))
                out = max(out, int(raw.get("output_tokens") or 0))
                cr = max(cr, int(raw.get("cache_read_input_tokens") or 0))
                cw = max(cw, int(raw.get("cache_creation_input_tokens") or 0))
                break

        if inp + out + cr + cw == 0:
            return None

        model_info = obj.get("model") or {}
        model = ""
        if isinstance(model_info, dict):
            model = str(model_info.get("modelId") or "")
        if not model:
            model = str(response.get("modelId") or "")

        rid = obj.get("requestId") or obj.get("traceId") or ""
        ts = parse_ts(obj.get("completedAt")) or parse_ts(obj.get("startedAt"))

        # 每次模型调用都带 durationMs（端到端），直接拿来当速度采样
        dur = int(obj.get("durationMs") or 0)
        if not dur:
            started = parse_ts(obj.get("startedAt"))
            if started and ts:
                dur = max(0, ts - started)
        self._sample(f"call:{rid or ts}", ts, model, kind="call",
                     duration_ms=dur, output_tokens=out)

        return UsageRecord(
            app=self.app,
            source=self.source,
            request_id=str(rid),
            ts_ms=ts,
            model=model,
            input_tokens=inp,
            output_tokens=out,
            cache_read_tokens=cr,
            cache_write_tokens=cw,
            session_id=str(obj.get("sessionId") or ""),
        )
