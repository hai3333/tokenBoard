#!/usr/bin/env python3
"""复现：按模型视图切换时间范围，用量是否变化。"""
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui.panel import PERIODS, Panel

ensure_dirs()
store = Store(DB_PATH)
panel = Panel(store, Scanner(store))
panel._view_idx = 1        # 按模型

print("=== 按模型视图：逐个时间范围 ===")
for idx, (name, _) in enumerate(PERIODS):
    panel._period_idx = idx
    panel._load()
    models = panel._rows
    top = models[0] if models else None
    tot = sum(r["tokens"] for r in models if r["kind"] == "model")
    print(f"  [{name:<4}] _since_day={panel._since_day()}  "
          f"模型数={len([r for r in models if r['kind'] == 'model']):>3}  "
          f"合计={tot / 1e6:>10.1f}M  "
          f"第一项={top['name'] if top else '-'}:{top['tokens'] / 1e6:.1f}M"
          if top else f"  [{name:<4}] 空")

print("\n=== 切回按工具视图对照 ===")
panel._view_idx = 0
for idx, (name, _) in enumerate(PERIODS):
    panel._period_idx = idx
    panel._load()
    tot = sum(r["tokens"] for r in panel._rows)
    print(f"  [{name:<4}] _since_day={panel._since_day()}  合计={tot / 1e6:>10.1f}M")

print("\n=== store 层直接查（排除面板逻辑）===")
for idx, (name, _) in enumerate(PERIODS):
    panel._period_idx = idx
    since = panel._since_day()
    ms = store.models_aggregated(since_day=since)
    tot = sum(m["total_tokens"] for m in ms)
    print(f"  [{name:<4}] since={since}  模型数={len(ms):>3}  合计={tot / 1e6:>10.1f}M")
