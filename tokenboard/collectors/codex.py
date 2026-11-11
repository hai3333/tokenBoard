"""Codex CLI 采集器：~/.codex/sessions/**/*.jsonl

Codex 有两套等价的用量记录，必须去重：
  1. outer type = "token_usage_record"      -> payload.usage      （带 response_id，优先）
  2. outer type = "event_msg", payload.type = "token_count"
                                          -> payload.info.last_token_usage

实测两者描述的是同一批请求（token 四元组一致、时间戳相差几毫秒），
但旧版本只写 token_count、新版本只写 token_usage_record，
因此取并集并按 (token 四元组 + 时间邻近) 去掉重叠。
"""
from __future__ import annotations

from datetime import datetime

from ..config import CODEX_DIR
from ..models import UsageRecord
from .base import BaseCollector, file_stat, iter_jsonl

# 两个来源的时间邻近阈值（毫秒）
NEAR_MS = 10_000


def parse_ts(value) -> int:
    if isinstance(value, (int, float)):
        return int(value if value > 1e11 else value * 1000)
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return 0


class CodexCollector(BaseCollector):
    app = "codex"
    source = "codex_session"

    def available(self) -> bool:
        return CODEX_DIR.is_dir()

    def collect(self) -> list[UsageRecord]:
        out: list[UsageRecord] = []
        self.samples = []
        if not CODEX_DIR.is_dir():
            return []

        for path in sorted(CODEX_DIR.rglob("*.jsonl")):
            locator = str(path)
            try:
                mtime, size = file_stat(locator)
            except OSError:
                continue
            if not self._file_changed(locator, locator, mtime, size):
                continue

            out.extend(self._parse_file(path))
            self._mark_synced(locator, locator, mtime, size)

        return out

    # ------------------------------------------------------------------
    def _parse_file(self, path) -> list[UsageRecord]:
        tur: list[UsageRecord] = []
        tc: list[UsageRecord] = []
        model = ""
        session_id = ""
        # 首字/耗时只有「整轮完成」事件给（task_complete），
        # 单条请求的日志没有耗时字段，所以速度按「轮」采样。
        cum_out = 0
        base_out = 0

        for obj in iter_jsonl(str(path)):
            outer = obj.get("type")
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue

            if outer == "turn_context":
                model = str(payload.get("model") or model)
                session_id = str(payload.get("session_id") or session_id)
                continue

            if outer == "session_meta":
                session_id = str(payload.get("id") or session_id)
                continue

            if outer == "token_usage_record":
                rec = self._from_usage(payload.get("usage"), payload, obj, model, session_id)
                if rec:
                    tur.append(rec)
                continue

            if outer != "event_msg":
                continue

            ptype = payload.get("type")
            if ptype == "token_count":
                info = payload.get("info") or {}
                total = info.get("total_token_usage")
                if isinstance(total, dict) and "output_tokens" in total:
                    cum_out = int(total.get("output_tokens") or 0)
                rec = self._from_usage(info.get("last_token_usage"), payload, obj,
                                       model, session_id)
                if rec:
                    tc.append(rec)
            elif ptype == "task_started":
                base_out = cum_out
            elif ptype == "task_complete":
                self._turn_sample(obj, payload, model, base_out, cum_out)

        return self._merge(tur, tc)

    def _turn_sample(self, obj: dict, payload: dict, model: str,
                     base_out: int, cum_out: int) -> None:
        """整轮完成 -> 一条速度采样（首字 + 端到端耗时）。"""
        ttft = int(payload.get("time_to_first_token_ms") or 0)
        dur = int(payload.get("duration_ms") or 0)
        ts = parse_ts(obj.get("timestamp"))
        if not ts:
            ts = int(float(payload.get("completed_at") or 0) * 1000)
        tid = (payload.get("turn_id") or payload.get("root_turn_id")
               or obj.get("ordinal") or "")
        # total_token_usage 是整条会话的累计值：本轮输出 = 完成时 - 开始时。
        # base_out 可能就是 0（会话第一轮），不能拿 falsy 判断。
        out = max(0, cum_out - base_out)
        self._sample(f"turn:{tid or ts}", ts, model, kind="turn",
                     ttft_ms=ttft, duration_ms=dur, output_tokens=out)

    def _from_usage(self, usage, payload, obj, model, session_id) -> UsageRecord | None:
        if not isinstance(usage, dict):
            return None
        raw_in = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        cached = int(usage.get("cached_input_tokens") or 0)
        cw = int(usage.get("cache_write_input_tokens") or 0)
        reasoning = int(usage.get("reasoning_output_tokens") or 0)
        if raw_in + out + cached + cw == 0:
            return None

        # Codex 用的是 OpenAI 口径：input_tokens 已经包含 cached_input_tokens，
        # 与 Anthropic 口径（input 不含 cache）正好相反。
        # 统一折算成「不含缓存的输入 + 单独的缓存读」，
        # 否则总 token 与费用都会把缓存重复计一次。
        inp = max(0, raw_in - cached)

        ts = parse_ts(obj.get("timestamp"))
        rid = (payload.get("response_id") or payload.get("turn_id")
               or f"{obj.get('ordinal')}")
        return UsageRecord(
            app=self.app,
            source=self.source,
            request_id=str(rid),
            ts_ms=ts,
            model=model,
            input_tokens=inp,
            output_tokens=out,
            cache_read_tokens=cached,
            cache_write_tokens=cw,
            reasoning_tokens=reasoning,
            session_id=session_id,
        )

    @staticmethod
    def _merge(tur: list[UsageRecord], tc: list[UsageRecord]) -> list[UsageRecord]:
        """token_count 中与 token_usage_record 重叠的记录丢弃。

        同一个 token 四元组可能对应多个真实请求（比如重复的相同提问），
        所以这里按「多重集」逐个配对，配对成功才算重复。
        """
        if not tc:
            return tur
        if not tur:
            return tc

        by_tuple: dict[tuple, list[int]] = {}
        for r in tur:
            key = (r.input_tokens, r.output_tokens, r.cache_read_tokens,
                   r.cache_write_tokens)
            by_tuple.setdefault(key, []).append(r.ts_ms)
        for stamps in by_tuple.values():
            stamps.sort()

        merged = list(tur)
        for r in tc:
            key = (r.input_tokens, r.output_tokens, r.cache_read_tokens,
                   r.cache_write_tokens)
            stamps = by_tuple.get(key)
            if not stamps:
                merged.append(r)
                continue
            # 找最近的一个尚未配对的 tur 时间戳
            best_i = -1
            best_delta = NEAR_MS + 1
            for i, ts in enumerate(stamps):
                delta = abs(ts - r.ts_ms)
                if delta < best_delta:
                    best_delta = delta
                    best_i = i
            if best_i >= 0 and best_delta <= NEAR_MS:
                stamps.pop(best_i)   # 同一请求的另一种记录形式，消耗掉这个配额
                continue
            merged.append(r)
        return merged
