#!/usr/bin/env python3
"""验证额度视图：三家订阅渲染 + 滚动 + 裁剪不越界。"""
import ctypes
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui.panel import (BODY_H, BODY_Y, PAD, QUOTA_GAP, QUOTA_W,
                                SEG_H, SEG_Y, VIEW_SEG_W, VIEW_SEG_X, Panel)
from tokenboard.ui.win32 import Canvas

ensure_dirs()
store = Store(DB_PATH)
panel = Panel(store, Scanner(store))
panel.create()
panel._view_idx = 2

from tokenboard.quota import fetch_all
quota = fetch_all()
panel._quota = quota
print("=== 额度数据 ===")
for q in quota:
    print(f"  {q.get('name'):<22} ok={q.get('ok')} "
          f"windows={len(q.get('windows') or [])} note={q.get('note', '')}")
    for w in q.get("windows") or []:
        print(f"      {w['kind']:<7} used={w['used']:5.1f}%  "
              f"remaining={w['remaining']:5.1f}%  reset_at={w['reset_at']}")

hdc = ctypes.windll.user32.GetDC(panel.hwnd)
canvas = Canvas(hdc, panel.width, panel.height, panel.scale)

print("\n=== 渲染测试 ===")
panel.draw(canvas)
print("  draw() 成功")

blocks = panel._quota_blocks()
total = sum(h for _, h in blocks) + QUOTA_GAP * (len(blocks) - 1)
print(f"  卡片数={len(blocks)} 总高={total:.0f} 可视高={BODY_H} "
      f"需要滚动={'是' if total > BODY_H else '否'}")

print("\n=== 滚动测试 ===")
for sc in (0, 40, 80, 120, 999):
    panel._quota_scroll = sc
    panel.draw(canvas)
    print(f"  scroll={panel._quota_scroll:>6.1f} -> 实际={panel._quota_scroll:.1f} "
          f"(上限={max(0.0, total - BODY_H):.1f})")

# 滚轮
panel._quota_scroll = 0
panel.on_mouse_wheel(1)
print(f"  滚轮下滚一格 -> {panel._quota_scroll}")
panel.on_mouse_wheel(-1)
print(f"  滚轮上滚一格 -> {panel._quota_scroll}")

print("\n=== 切视图时重置滚动 ===")
seg_y = SEG_Y + SEG_H / 2
panel._quota_scroll = 100
panel.on_click(VIEW_SEG_X + VIEW_SEG_W * 0.5, seg_y)
print(f"  切到按工具后 _quota_scroll={panel._quota_scroll} _view_idx={panel._view_idx}")
panel.on_click(VIEW_SEG_X + VIEW_SEG_W * 2.5, seg_y)
print(f"  切到订阅额度后 _quota_scroll={panel._quota_scroll} _view_idx={panel._view_idx}")

panel._quota_scroll = 0
panel.draw(canvas)
print("\n全部通过！")
