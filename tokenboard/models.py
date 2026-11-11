"""统一用量记录模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class UsageRecord:
    """一条请求级别的 token 用量记录。

    所有采集器把各自格式归一化成这个结构。
    """

    app: str                       # claude / codex / mcode / opencode / zcode / dsh
    source: str                    # 采集器名，用于溯源
    request_id: str                # 去重键（同一 app 内唯一）
    ts_ms: int                     # 时间戳（epoch 毫秒）
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    session_id: str = ""
    project: str = ""

    @property
    def total_tokens(self) -> int:
        """总 token = 输入 + 输出 + 缓存读 + 缓存写（与各家 totalTokens 口径一致）。"""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    @property
    def day(self) -> str:
        return datetime.fromtimestamp(self.ts_ms / 1000).strftime("%Y-%m-%d")


@dataclass(slots=True)
class SpeedSample:
    """一次「响应速度」采样。

    为什么和 UsageRecord 分开存：两边粒度不一样。
      * 用量是请求级的，各家日志都有；
      * 速度有的源只给到「轮」级（Codex 的 task_complete），有的给到
        「单次调用」级（ZCode / OpenCode / DSH）。
    混进同一张表会让 token 有被重复累加的风险，所以单独存一份采样，
    聚合时按 app / model 各算各的。
    """

    app: str
    source: str
    sample_id: str                 # 去重键（同一 app 内唯一）
    ts_ms: int
    model: str = ""
    kind: str = "call"             # call = 单次模型调用；turn = 一整轮（含工具）
    ttft_ms: int = 0               # 首字耗时（0 = 该来源不提供）
    duration_ms: int = 0           # 端到端耗时
    output_tokens: int = 0         # 用来算 tok/s

    @property
    def day(self) -> str:
        return datetime.fromtimestamp(self.ts_ms / 1000).strftime("%Y-%m-%d")


@dataclass(slots=True)
class ScanResult:
    """一次扫描的结果。"""

    app: str
    ok: bool = True
    error: str = ""
    new_records: int = 0
    new_samples: int = 0
    scanned_files: int = 0
    duration_ms: int = 0
    detail: str = ""
    records: list[UsageRecord] = field(default_factory=list)
    speed_samples: list[SpeedSample] = field(default_factory=list)
