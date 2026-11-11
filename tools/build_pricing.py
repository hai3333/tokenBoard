#!/usr/bin/env python3
"""生成 tokenboard/data/pricing.json。

以 CC Switch 的 model_pricing 表为基础（价格口径一致），再补齐本机实际出现
但 CC Switch 表里没有的模型，最后加上按前缀回退的兜底价格。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tokenboard" / "data" / "pricing.json"
CC_DB = os.path.expanduser("~/.cc-switch/cc-switch.db")

# 兜底价格（美元 / 百万 token）：用于表里完全没有的模型
FALLBACKS: dict[str, dict] = {
    "deepseek": {"input": 0.28, "output": 1.11, "cache_read": 0.028},
    "glm": {"input": 1.40, "output": 4.40, "cache_read": 0.26},
    "qwen": {"input": 0.65, "output": 1.95, "cache_read": 0.13},
    "kimi": {"input": 0.95, "output": 4.00, "cache_read": 0.16},
    "minimax": {"input": 0.31, "output": 1.25, "cache_read": 0.06},
    "gpt": {"input": 5.00, "output": 30.00, "cache_read": 0.50},
    "claude": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "gemini": {"input": 1.25, "output": 10.00, "cache_read": 0.31},
    "doubao": {"input": 0.80, "output": 2.00, "cache_read": 0.08},
    "grok": {"input": 3.00, "output": 15.00, "cache_read": 0.75},
    "hunyuan": {"input": 0.80, "output": 2.00, "cache_read": 0.08},
    "mistral": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "step": {"input": 1.00, "output": 3.00, "cache_read": 0.10},
    "big-pickle": {"input": 0.0, "output": 0.0, "cache_read": 0.0},
}

# 本机实际出现过、CC Switch 表里没有的模型 -> 价格
EXTRA: dict[str, dict] = {
    "glm-5.3-flash": {"input": 0.15, "output": 0.50, "cache_read": 0.03},
    "glm-5-3-flash": {"input": 0.15, "output": 0.50, "cache_read": 0.03},
    "glm-5-3-flashx": {"input": 0.37, "output": 1.25, "cache_read": 0.075},
    "deepseek-v4-pro": {"input": 0.66, "output": 1.98, "cache_read": 0.022},
    "deepseek-v4-flash": {"input": 0.30, "output": 1.20, "cache_read": 0.006},
    "deepseek-v4-flash-ga-260731": {"input": 0.30, "output": 1.20, "cache_read": 0.006},
    "deepseek-v4-flash-free": {"input": 0.0, "output": 0.0, "cache_read": 0.0},
    "deepseek-flash": {"input": 0.15, "output": 0.60, "cache_read": 0.003},
    "qwen3.8-max": {"input": 2.00, "output": 6.00, "cache_read": 0.25},
    "qwen3.8-flash": {"input": 0.15, "output": 0.47, "cache_read": 0.016},
    "qwen3.8:latest": {"input": 2.00, "output": 6.00, "cache_read": 0.25},
    "qianfan-code-latest": {"input": 1.00, "output": 3.00, "cache_read": 0.10},
    "doubao-seed-2.0-code": {"input": 0.80, "output": 2.00, "cache_read": 0.08},
    "kimi-k2.8-preview": {"input": 0.95, "output": 4.00, "cache_read": 0.16},
    "kimi-for-coding": {"input": 0.95, "output": 4.00, "cache_read": 0.16},
    "gemini-3.8-flash-high": {"input": 0.15, "output": 0.47, "cache_read": 0.016},
    "ling-2.6-flash-free": {"input": 0.0, "output": 0.0, "cache_read": 0.0},
    "hy3-preview-free": {"input": 0.0, "output": 0.0, "cache_read": 0.0},
    "gpt-5.6-sol": {"input": 5.00, "output": 30.00, "cache_read": 0.50},
    "gpt-5.6-terra": {"input": 5.00, "output": 30.00, "cache_read": 0.50},
    "gpt-5.6-luna": {"input": 5.00, "output": 30.00, "cache_read": 0.50},
    "gpt-6-astra": {"input": 5.00, "output": 30.00, "cache_read": 0.50},
    "codex-auto-review": {"input": 5.00, "output": 30.00, "cache_read": 0.50},
}


def main() -> int:
    payload: dict[str, dict] = {}

    if Path(CC_DB).exists():
        conn = sqlite3.connect(f"file:{CC_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        for r in conn.execute("SELECT * FROM model_pricing"):
            try:
                payload[r["model_id"]] = {
                    "display_name": r["display_name"],
                    "input": float(r["input_cost_per_million"] or 0),
                    "output": float(r["output_cost_per_million"] or 0),
                    "cache_read": float(r["cache_read_cost_per_million"] or 0),
                    "cache_write": float(r["cache_creation_cost_per_million"] or 0),
                }
            except (TypeError, ValueError):
                continue
        conn.close()
        print(f"loaded {len(payload)} rows from CC Switch model_pricing")
    else:
        print("CC Switch db not found, using extras + fallbacks only")

    for k, v in EXTRA.items():
        payload.setdefault(k, {"display_name": k, "cache_write": 0.0, **v})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    print(f"wrote {OUT}  ({len(payload)} models)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
