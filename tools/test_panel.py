#!/usr/bin/env python3
"""下钻交互自检：展开/收起、滚动、跨视图。"""
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui.panel import (APP_NAME_X, BODY_Y, PERIODS, SEG_X, SEG_W,
                                 SEG_Y, VIEW_SEG_X, VIEW_SEG_W, VIEW_SEG_Y,
                                 VIEWS, Panel)

ensure_dirs()
store = Store(DB_PATH)
panel = Panel(store, Scanner(store))

print("=== 按工具视图 ===")
panel._view_idx = 0
panel._load()
print(f"  未展开时行数: {len(panel._rows)}")
for i, r in enumerate(panel._rows):
    print(f"    [{i}] {r['name']:<10} {r['tokens'] / 1e6:>9.1f}M")

# 找到 OpenCode 那一行并点它
idx = next(i for i, r in enumerate(panel._rows) if r["name"] == "OpenCode")
panel.on_click(APP_NAME_X + 20, panel._row_y[idx] + 10)
panel._load()
print(f"\n  展开 OpenCode 后行数: {len(panel._rows)}")
for r in panel._rows:
    if r["kind"] == "sub":
        print(f"    └ {r['name']:<34} {r['tokens'] / 1e6:>9.1f}M  {r['pct']:5.1f}%")

print("\n=== 收起 ===")
panel.on_click(APP_NAME_X + 20, panel._row_y[idx] + 10)
panel._load()
print(f"  收起后行数: {len(panel._rows)}")

print("\n=== 展开多个 ===")
for i in range(3):
    panel.on_click(APP_NAME_X + 20, BODY_Y + 10 + i * 40)
panel._load()
print(f"  行数: {len(panel._rows)}  子行数: {sum(1 for r in panel._rows if r['kind'] == 'sub')}")

print("\n=== 按模型视图（点模型展开用到哪些工具）===")
panel.on_click(VIEW_SEG_X + VIEW_SEG_W + 10, VIEW_SEG_Y + 5)
panel._load()
print(f"  模型视图行数: {len(panel._rows)}")
# 展开第一个模型
panel.on_click(APP_NAME_X + 20, BODY_Y + 10)
panel._load()
print(f"  展开后行数: {len(panel._rows)}")
for r in panel._rows[:8]:
    tag = "└" if r["kind"] == "sub" else " "
    extra = f"  {r['pct']:.1f}%" if r["kind"] == "sub" else ""
    print(f"    {tag} {r['name']:<34} {r['tokens'] / 1e6:>9.1f}M{extra}")

print("\n=== 滚动 ===")
panel._scroll = 0
for _ in range(3):
    panel.on_mouse_wheel(1)
print(f"  滚 3 格后 _scroll={panel._scroll}")
panel.on_mouse_wheel(-1)
print(f"  回滚 1 格后 _scroll={panel._scroll}")

print("\n=== 时间范围切换会清空展开 ===")
panel.on_click(SEG_X + 2 * SEG_W + 10, SEG_Y + 10)
print(f"  切到「{PERIODS[2][0]}」后 _expanded={panel._expanded} _scroll={panel._scroll}")
print("\n自检通过")
