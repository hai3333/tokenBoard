"""一次性回填：清水位 + 全量扫描（验证速度采样/成本）。"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.pricing import get_pricing
from tokenboard.scanner import Scanner
from tokenboard.store import Store

ensure_dirs()
store = Store(DB_PATH)
store.load_pricing(get_pricing().pricing_map())
print("清空扫描水位 ...")
store.clear_sync()
t0 = time.time()
scanner = Scanner(store)
results = scanner.scan()
print(f"扫描完成 {time.time() - t0:.1f}s")
for r in results:
    print(f"  {r.app:<10} {'OK ' if r.ok else 'ERR'} {r.duration_ms:>6}ms "
          f"用量 {r.new_records:>6}  速度 {r.new_samples:>5}  {r.error}")
print("用量行:", store.count_usage(), " 速度采样:", store.count_speed())
store.close()