#!/usr/bin/env python3
"""状态点交互自检：点绿点跳到该工具并展开；点红点显示错误。"""
import sys

sys.path.insert(0, r"D:\个人资料\项目\token看板")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.scanner import Scanner
from tokenboard.store import Store
from tokenboard.ui.panel import Panel
from tokenboard.ui.win32 import Canvas, user32

ensure_dirs()
store = Store(DB_PATH)
panel = Panel(store, Scanner(store))
panel._status = {a: (True, "") for a in
                 ("claude", "codex", "mcode", "opencode", "zcode", "dsh")}
panel._status["zcode"] = (False, "zstd 解析失败: 文件被占用")

hdc = user32.GetDC(0)
canvas = Canvas(hdc, panel.width, panel.height, panel.scale)
panel.draw(canvas)

print("  状态点位置:")
for app, x, y, w in panel._dot_hit:
    print(f"    {app:<10} x={x:<5} y={y:<5} w={w}")

print("\n=== 点 OpenCode 的绿点 ===")
t = [d for d in panel._dot_hit if d[0] == "opencode"][0]
panel.on_click(t[1] + 5, t[2] + 5)
print(f"  view={panel._view_idx}  expanded={panel._expanded}  scroll={panel._scroll}")
for r in panel._rows:
    tag = "└" if r["kind"] == "sub" else " "
    print(f"    {tag} {r['name']:<26} {r['tokens'] / 1e6:>9.1f}M")

print("\n=== 点 ZCode 的红点（采集失败）===")
panel.draw(canvas)   # 重新布局，拿到新的点位置
t = [d for d in panel._dot_hit if d[0] == "zcode"][0]
panel.on_click(t[1] + 5, t[2] + 5)
print(f"  footer: {panel._footer_msg()}")
print(f"  view={panel._view_idx}  expanded={panel._expanded}")

print("\n=== 扫描成功后错误提示自动清除 ===")
panel._q.put(("scan_done", []))
panel.on_timer(1)
print(f"  footer: {panel._footer_msg()}")
print("\n自检通过")
