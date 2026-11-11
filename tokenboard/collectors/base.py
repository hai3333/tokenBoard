"""采集器基类与公共工具。"""
from __future__ import annotations

import json
import os
import time
from typing import Iterator

from ..models import SpeedSample, UsageRecord


class BaseCollector:
    """所有采集器的公共接口。

    子类实现 collect()，返回 UsageRecord 列表；顺手把速度采样塞进
    self.samples（每次 collect 开头要清空）。
    """

    app: str = ""
    source: str = ""

    def __init__(self, store):
        self.store = store
        self.samples: list[SpeedSample] = []

    # 子类可覆盖
    def available(self) -> bool:
        return True

    def collect(self) -> list[UsageRecord]:  # pragma: no cover - 子类实现
        raise NotImplementedError

    # ---------------------------------------------------------------- 工具
    def _sample(self, sample_id: str, ts_ms: int, model: str = "",
                kind: str = "call", ttft_ms: int = 0, duration_ms: int = 0,
                output_tokens: int = 0) -> None:
        """记一条速度采样（没有耗时信息就不用记）。"""
        if duration_ms <= 0 and ttft_ms <= 0:
            return
        if not ts_ms:
            return
        self.samples.append(SpeedSample(
            app=self.app, source=self.source, sample_id=sample_id,
            ts_ms=int(ts_ms), model=model or "", kind=kind,
            ttft_ms=int(ttft_ms or 0), duration_ms=int(duration_ms or 0),
            output_tokens=int(output_tokens or 0),
        ))
    def _file_changed(self, locator: str, path: str, mtime: float, size: int) -> bool:
        """文件是否变化（用于增量跳过）。"""
        row = self.store.get_sync(self.app, locator)
        if row is None:
            return True
        return int(row["size"]) != size or abs(float(row["mtime"]) - mtime) > 0.001

    def _mark_synced(self, locator: str, path: str, mtime: float, size: int,
                     watermark: int = 0) -> None:
        self.store.set_sync(self.app, locator, mtime, size, watermark)


def iter_jsonl(path: str) -> Iterator[dict]:
    """逐行读取 JSONL，容忍坏行。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                yield obj


def file_stat(path: str) -> tuple[float, int]:
    try:
        st = os.stat(path)
        return st.st_mtime, st.st_size
    except OSError:
        return 0.0, 0


def now_ms() -> int:
    return int(time.time() * 1000)
