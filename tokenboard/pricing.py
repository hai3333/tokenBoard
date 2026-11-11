"""模型价格解析。

优先级：精确匹配 -> 归一化匹配（去厂商前缀/后缀修饰） -> 家族前缀回退。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import PRICING_PATH


class PricingTable:
    def __init__(self, payload: dict[str, dict] | None = None):
        self._exact: dict[str, dict] = {}
        self._family: list[tuple[str, dict]] = []
        self._raw: dict[str, dict] = {}
        if payload is None:
            payload = self._load()
        self._raw = payload
        for model_id, p in payload.items():
            self._exact[model_id.lower()] = p
            self._exact[self._normalize(model_id)] = p
        # 家族前缀：长前缀优先，避免 gpt-5 抢占 gpt-5.6-sol
        families = sorted(self._exact.items(), key=lambda kv: -len(kv[0]))
        self._family = [(k, v) for k, v in families if len(k) >= 3]

    # ------------------------------------------------------------------
    def raw(self) -> dict[str, dict]:
        """原始价格表（model_id -> 价格字典）。"""
        return dict(self._raw)

    def pricing_map(self) -> dict[str, dict]:
        """扁平价格表（model_id -> {input,output,cache_read,cache_write}）。"""
        return {
            mid: {
                "input": p.get("input", 0),
                "output": p.get("output", 0),
                "cache_read": p.get("cache_read", 0),
                "cache_write": p.get("cache_write", 0),
            }
            for mid, p in self._raw.items()
        }

    @staticmethod
    def _load() -> dict[str, dict]:
        try:
            return json.loads(Path(PRICING_PATH).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    def _normalize(model_id: str) -> str:
        s = (model_id or "").strip().lower()
        s = s.split("/")[-1]                      # ZHIPU/GLM-5.3 -> glm-5.3
        s = re.sub(r"[-_]?(high|low|medium|max|mini|flash|free|preview|turbo|thinking|"
                   r"reasoning|xhigh|highspeed|lightning|latest)$", "", s)
        s = re.sub(r"[-_]?\d{6,}$", "", s)        # 去掉日期后缀
        return s.strip("-_")

    def resolve(self, model_id: str) -> dict | None:
        if not model_id:
            return None
        raw = model_id.strip().lower()
        if raw in self._exact:
            return self._exact[raw]

        norm = self._normalize(model_id)
        if norm in self._exact:
            return self._exact[norm]

        # 家族前缀回退
        for key, price in self._family:
            if norm.startswith(key):
                return price
        for key, price in self._family:
            if key.startswith(norm):
                return price
        return None

    def cost(self, model_id: str, input_tokens: int, output_tokens: int,
             cache_read: int = 0, cache_write: int = 0) -> float:
        p = self.resolve(model_id)
        if not p:
            return 0.0
        return (
            input_tokens * p.get("input", 0)
            + output_tokens * p.get("output", 0)
            + cache_read * p.get("cache_read", 0)
            + cache_write * p.get("cache_write", 0)
        ) / 1_000_000


_SINGLETON: PricingTable | None = None


def get_pricing() -> PricingTable:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = PricingTable()
    return _SINGLETON
