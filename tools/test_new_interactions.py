"""新交互自检：搜索过滤 + 右键菜单 + 快捷键提示。

跑法：python tools/test_new_interactions.py
（会临时开一个窗口，测试完自动关闭）
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from tokenboard.config import DB_PATH  # noqa: E402
from tokenboard.pricing import get_pricing  # noqa: E402
from tokenboard.scanner import Scanner  # noqa: E402
from tokenboard.store import Store  # noqa: E402
from tokenboard.ui import panel as P  # noqa: E402
from tokenboard.ui.win32 import MSG, user32  # noqa: E402

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  ✅ " if cond else "  ❌ ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        failures.append(name)


def pump(ms: int) -> None:
    msg = MSG()
    end = time.time() + ms / 1000
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)


def main() -> int:
    store = Store(DB_PATH)
    store.load_pricing(get_pricing().pricing_map())
    scanner = Scanner(store)
    p = P.Panel(store, scanner)
    p.create()
    p.show()
    pump(1500)

    print("1) 搜索框")
    rect = p._search_rect()
    check("搜索框在标题栏内", rect[1] >= 0 and rect[1] + rect[3] <= P.TITLE_H,
          str(rect))
    check("搜索框初始未聚焦", p._search_focus is False)
    p.on_click(rect[0] + 5, rect[1] + rect[3] / 2)
    check("点搜索框获得焦点", p._search_focus is True)
    n0 = len(p._rows)
    for ch in "claude":
        p.on_char(ch)
    check("on_char 累积输入", p._search_q == "claude", p._search_q)
    check("输入未聚焦时 on_char 不消费", p.on_char("x") is True)
    p.on_key(0x1B)          # Esc via on_key path（搜索聚焦时）
    pump(80)
    # Esc in on_key only flips focus；再按 Esc 清空走 on_char
    p._search_focus = True
    p.on_char("\x1b")
    check("Esc 清空搜索词", p._search_q == "")
    check("Esc 退出输入态", p._search_focus is False)

    print("2) 搜索过滤行为")
    p._search_focus = True
    for ch in "zz_nonexistent_xyz":
        p.on_char(ch)
    p._load()
    check("无命中时列表为空", len(p._rows) == 0)
    p._search_q = ""
    p._search_focus = False
    p._load()
    check("清空搜索后行数恢复", len(p._rows) == n0, f"{len(p._rows)} vs {n0}")

    print("3) 右键菜单")
    # 找第一个非子行
    target = next((r for r in p._rows if r["kind"] not in ("sub", "ssub")), None)
    check("存在可右键行", target is not None)
    if target:
        i = next(i for i, r in enumerate(p._rows) if r is target)
        rx, ry, rw, rh = p._row_rect(i)
        p.on_right_click(rx + 30, ry + rh / 2)
        check("右键打开菜单", len(p._ctx_items) > 0, str([m for m, _ in p._ctx_items]))
        check("菜单目标行已记录", p._ctx_row == i)
        # 执行 “只看 xxx”（filter）
        fidx = next(k for k, (m, _) in enumerate(p._ctx_items) if m == "filter")
        p.on_click(p._ctx_x + 10, p._ctx_y + 6 + fidx * 26.0 + 13)
        check("选择“只看”后过滤生效", p._search_q == target.get("name"), p._search_q)
        check("菜单执行后关闭", p._ctx_items == [])
        check("过滤后进入输入态", p._search_focus is True)
        # 再开一次菜单并执行 collapse/expand 之一
        p._search_q = ""
        p._search_focus = False
        p._load()
        target = next((r for r in p._rows if r["kind"] not in ("sub", "ssub")), None)
        i = next(i for i, r in enumerate(p._rows) if r is target)
        rx, ry, rw, rh = p._row_rect(i)
        was_open = target["key"] in p._expanded
        p.on_right_click(rx + 30, ry + rh / 2)
        eidx = next(k for k, (m, _) in enumerate(p._ctx_items)
                    if m in ("expand", "collapse"))
        p.on_click(p._ctx_x + 10, p._ctx_y + 6 + eidx * 26.0 + 13)
        now_open = target["key"] in p._expanded
        check("菜单展开/收起生效", now_open != was_open)

    print("4) R 刷新键入口")
    p._search_focus = False
    p.on_key(0x52)   # 不应抛异常
    pump(200)
    check("R 触发扫描不崩溃", True)

    p.destroy()
    print()
    if failures:
        print(f"FAILED: {len(failures)}: {failures}")
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
