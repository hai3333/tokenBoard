"""扫描调度：依次跑各采集器，算成本，写库。"""
from __future__ import annotations

import time
import traceback

from .collectors import build_collectors
from .models import ScanResult, UsageRecord
from .pricing import get_pricing
from .store import Store


def trim_working_set() -> None:
    """扫描完把工作集收缩，把解析日志用的临时内存还给系统。

    Python 的分配器会一直占着已释放的 arena，不收缩的话任务管理器里
    常驻内存会一直停在峰值（实测差 10MB+）。
    """
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32")
        psapi = ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        psapi.EmptyWorkingSet(k32.GetCurrentProcess())
    except Exception:  # noqa: BLE001
        pass


class Scanner:
    def __init__(self, store: Store):
        self.store = store
        self.pricing = get_pricing()
        self.collectors = build_collectors(store)
        self.last_results: list[ScanResult] = []

    # ------------------------------------------------------------------
    def scan(self, apps: list[str] | None = None) -> list[ScanResult]:
        results: list[ScanResult] = []
        for col in self.collectors:
            if apps and col.app not in apps:
                continue
            t0 = time.time()
            res = ScanResult(app=col.app)
            try:
                if not col.available():
                    res.ok = False
                    res.error = "未安装或路径不存在"
                else:
                    records = col.collect()
                    self._apply_cost(records)
                    inserted = self.store.upsert_usage(records)
                    res.new_records = inserted
                    res.records = records
                    samples = getattr(col, "samples", [])
                    if samples:
                        self.store.upsert_speed(samples)
                        res.new_samples = len(samples)
                        res.speed_samples = samples
            except Exception as e:  # noqa: BLE001
                res.ok = False
                res.error = f"{type(e).__name__}: {e}"
                res.detail = traceback.format_exc(limit=3)
            res.duration_ms = int((time.time() - t0) * 1000)
            results.append(res)

        self.last_results = results
        trim_working_set()
        return results

    # ------------------------------------------------------------------
    def _apply_cost(self, records: list[UsageRecord]) -> None:
        for r in records:
            if r.cost_usd and r.cost_usd > 0:
                continue
            r.cost_usd = self.pricing.cost(
                r.model, r.input_tokens, r.output_tokens,
                r.cache_read_tokens, r.cache_write_tokens,
            )

    # ------------------------------------------------------------------
    def status(self) -> dict[str, ScanResult]:
        return {r.app: r for r in self.last_results}
