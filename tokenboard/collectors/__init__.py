"""采集器注册表。"""
from __future__ import annotations

from .base import BaseCollector
from .claude import ClaudeCollector
from .codex import CodexCollector
from .dsh import DshCollector
from .mcode import MCodeCollector
from .opencode import OpenCodeCollector
from .zcode import ZCodeCollector

COLLECTOR_CLASSES = [
    ClaudeCollector,
    CodexCollector,
    MCodeCollector,
    OpenCodeCollector,
    ZCodeCollector,
    DshCollector,
]


def build_collectors(store) -> list[BaseCollector]:
    return [cls(store) for cls in COLLECTOR_CLASSES]


__all__ = ["COLLECTOR_CLASSES", "build_collectors", "BaseCollector"]
