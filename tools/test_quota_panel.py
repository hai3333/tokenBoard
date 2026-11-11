#!/usr/bin/env python3
"""在进程内跑面板，看扫描/额度线程到底有没有回结果。"""
import sys
import time

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui.panel import Panel

ensure_dirs()
store = Store(DB_PATH)
panel = Panel(store, Scanner(store))

print("直接调 fetch_all():")
try:
    from tokenboard.quota import fetch_all
    for q in fetch_all():
        print(f"   {q['name']}: ok={q['ok']} wins={len(q['windows'])} err={q.get('error','')[:60]}")
except Exception as e:  # noqa: BLE001
    import traceback
    traceback.print_exc()

print("\n走面板的 _start_quota():")
panel._start_quota()
for _ in range(10):
    time.sleep(0.5)
    panel.on_timer(1)          # 手动驱动一次消息泵
print("   panel._quota =", panel._quota)
print("   panel._status =", panel._status)
