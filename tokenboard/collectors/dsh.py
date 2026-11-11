"""DeepSeek Harness 采集器：~/.dsh/sessions/**/session*.jsonl.zstd

CC Switch 看不到 DeepSeek Harness —— 这是本插件新增的采集源。

要点：
  * 会话日志是 **多帧 zstd** 压缩流（不是单帧），必须用 stream_reader 逐帧读完，
    否则只能拿到第一帧的 session 头。
  * 每行形如 {"type":..., "seq":..., "time":..., "data":"<json字符串>"}
    —— data 是嵌套的 JSON 字符串，需要二次解析。
  * 用量在 data.usage：inputTokens / outputTokens / totalTokens /
    cacheReadTokens / cacheWriteTokens，挂在 type="assistant/message" 的记录上。
  * data.stream[N].chunk.usage 是流式分片里的同一份用量，**不能重复累加**，
    因此这里只取 data.usage。
"""
from __future__ import annotations

import json

from ..config import DSH_DIR
from ..models import UsageRecord
from .base import BaseCollector, file_stat

try:
    import zstandard
    _HAS_ZSTD = True
except Exception:  # noqa: BLE001
    _HAS_ZSTD = False


class DshCollector(BaseCollector):
    app = "dsh"
    source = "dsh_session"

    def available(self) -> bool:
        return _HAS_ZSTD and DSH_DIR.is_dir()

    def collect(self) -> list[UsageRecord]:
        out: list[UsageRecord] = []
        self.samples = []
        if not self.available():
            return []

        dctx = zstandard.ZstdDecompressor()
        for path in sorted(DSH_DIR.rglob("*.zstd")):
            locator = str(path)
            try:
                mtime, size = file_stat(locator)
            except OSError:
                continue
            if not self._file_changed(locator, locator, mtime, size):
                continue

            out.extend(self._parse_file(path, dctx))
            self._mark_synced(locator, locator, mtime, size)

        return out

    # ------------------------------------------------------------------
    def _parse_file(self, path, dctx) -> list[UsageRecord]:
        records: list[UsageRecord] = []
        session_id = path.parent.name  # session-<uuid>
        current_model = ""           # 用量记录本身不带模型，靠前序记录带出来
        # 耗时口径：step/start 是模型调用开始，assistant/message 是整条消息落盘
        # （紧随其后的 tool/call 才解析工具调用），两者之差就是这次调用的耗时。
        step_start = 0

        try:
            with open(path, "rb") as f:
                # read_across_frames=True：把拼接的多帧全部读出来
                raw = dctx.stream_reader(f, read_across_frames=True).readall()
        except Exception:  # noqa: BLE001
            return records

        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(obj, dict):
                continue

            data = obj.get("data")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:  # noqa: BLE001
                    continue
            if not isinstance(data, dict):
                continue

            # 记录当前会话使用的模型（model/selection、request/header 等）
            found = _extract_model(data)
            if found:
                current_model = found

            typ = str(obj.get("type") or "")
            ts = int(obj.get("time") or 0)
            if typ == "step/start":
                step_start = ts
                continue

            usage = data.get("usage")
            if not isinstance(usage, dict):
                continue

            inp = int(usage.get("inputTokens") or 0)
            out = int(usage.get("outputTokens") or 0)
            cr = int(usage.get("cacheReadTokens") or 0)
            cw = int(usage.get("cacheWriteTokens") or 0)
            if inp + out + cr + cw == 0:
                continue

            seq = obj.get("seq")
            rid = f"{session_id}:{seq}" if seq is not None else f"{session_id}:{ts}"

            # 模型调用耗时：step/start -> assistant/message
            if step_start and ts > step_start:
                self._sample(f"call:{rid}", ts, current_model, kind="call",
                             duration_ms=ts - step_start, output_tokens=out)

            records.append(UsageRecord(
                app=self.app,
                source=self.source,
                request_id=str(rid),
                ts_ms=ts,
                model=current_model,
                input_tokens=inp,
                output_tokens=out,
                cache_read_tokens=cr,
                cache_write_tokens=cw,
                session_id=str(data.get("sessionId") or session_id),
                project=str(obj.get("cwd") or ""),
            ))

        return records


def _extract_model(data: dict) -> str:
    """从记录里挖出模型名（字段名各版本不一致，尽量兼容）。"""
    for key in ("modelId", "model", "modelName"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict):
            for sub in ("modelId", "id", "name", "model"):
                s = val.get(sub)
                if isinstance(s, str) and s:
                    return s
    # {"fromModel": {...}, "toModel": {...}}
    for key in ("toModel", "fromModel"):
        val = data.get(key)
        if isinstance(val, dict):
            s = val.get("modelID") or val.get("modelId") or val.get("id")
            if isinstance(s, str) and s:
                return s
    return ""
