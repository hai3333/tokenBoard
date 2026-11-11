#!/usr/bin/env python3
"""深度验证（深色版布局）：
1. 分段控件悬停是否触发手型光标（on_set_cursor 返回 True）
2. 模拟点击「订阅额度」，检查 draw() 是否抛出任何异常
3. 模拟点击「按模型」以及各个时间范围，检查 draw() 和数据联动
"""
import ctypes
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui.panel import (PAD, HEAD_H, SEG_H, SEG_Y,
                                VIEW_SEG_W, VIEW_SEG_X,
                                PERIOD_SEG_W, PERIOD_SEG_X,
                                VIEWS, PERIODS, Panel)

ensure_dirs()
store = Store(DB_PATH)
scanner = Scanner(store)
panel = Panel(store, scanner)
panel.create()

print("=== 1. 验证光标手型命中测试 ===")
# 悬停在「订阅额度」按钮中心（第 3 个视图分段）
test_x = VIEW_SEG_X + VIEW_SEG_W * 2.5
test_y = SEG_Y + SEG_H / 2
is_hand = panel.on_set_cursor((test_x, test_y))
print(f"悬停在「订阅额度」中心 ({test_x}, {test_y}): is_hand={is_hand}")
assert is_hand, "悬停在「订阅额度」上必须显示手型光标！"

# 悬停在时间范围「7 天」
test_x2 = PERIOD_SEG_X + PERIOD_SEG_W * 1.5
test_y2 = SEG_Y + SEG_H / 2
is_hand2 = panel.on_set_cursor((test_x2, test_y2))
print(f"悬停在时间范围「7天」中心 ({test_x2}, {test_y2}): is_hand={is_hand2}")
assert is_hand2, "悬停在时间控件上必须显示手型光标！"

# 悬停在两个分段控件之间的空白处
blank_x = (VIEW_SEG_X + VIEW_SEG_W * len(VIEWS) + PERIOD_SEG_X) // 2
is_hand_blank = panel.on_set_cursor((blank_x, test_y))
print(f"悬停在空白处 ({blank_x}, {test_y}): is_hand={is_hand_blank}")
assert not is_hand_blank, "悬停在空白处不能显示手型光标！"

print("=== 2. 验证点击「订阅额度」绘制与异常 ===")
click_x = VIEW_SEG_X + VIEW_SEG_W * 2.5
click_y = SEG_Y + SEG_H / 2
panel.on_click(click_x, click_y)
print(f"已点击「订阅额度」: 当前 _view_idx={panel._view_idx}")
assert panel._view_idx == 2, f"预期 _view_idx==2，实际 {panel._view_idx}"

# 模拟接收到 MiniMax 和火山额度数据
from tokenboard.quota import fetch_all
quotas = fetch_all()
panel._quota = quotas
print(f"已拉取到 {len(quotas)} 个订阅额度项:")
for q in quotas:
    print(f"  - {q.get('name')}: ok={q.get('ok')}, windows={len(q.get('windows') or [])}")

# 执行绘制，验证是否抛出任何异常
print("执行 draw()...")
from tokenboard.ui.win32 import Canvas
canvas = Canvas(ctypes.windll.user32.GetDC(panel.hwnd), panel.width, panel.height, panel.scale)
panel.draw(canvas)
print("draw() 绘制「订阅额度」成功，无异常！")

print("=== 3. 验证切回「按模型」与时间范围联动 ===")
panel.on_click(VIEW_SEG_X + VIEW_SEG_W * 1.5, click_y)
assert panel._view_idx == 1, "切回按模型失败"

for i, (pname, _) in enumerate(PERIODS):
    px = PERIOD_SEG_X + PERIOD_SEG_W * i + PERIOD_SEG_W / 2
    py = SEG_Y + SEG_H / 2
    panel.on_click(px, py)
    assert panel._period_idx == i, f"时间范围 [{pname}] 选中失败"
    panel.draw(canvas)
    print(f"时间范围 [{pname}]: total={panel._totals['total'] / 1e6:.1f}M, rows={len(panel._rows)}")

print("=== 4. 验证「按工具」视图 ===")
panel.on_click(VIEW_SEG_X + VIEW_SEG_W * 0.5, click_y)
assert panel._view_idx == 0, "切回按工具失败"
panel.draw(canvas)
print(f"按工具视图: total={panel._totals['total'] / 1e6:.1f}M, rows={len(panel._rows)}")

print("\n全部验证通过！界面交互与绘制完全正常！")
panel.destroy()
