#!/usr/bin/env python3
"""主面板交互回归：改版后所有命中区域都挪过位置，这里逐个点一遍。

只读真实数据库（不扫描、不写库），窗口建完就销毁。

    python tools/test_panel_ui.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ok_count = 0
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok_count
    if cond:
        ok_count += 1
        print(f"[ OK ] {name}")
    else:
        failures.append(name)
        print(f"[FAIL] {name}  {detail}")


def center(rect):
    x, y, w, h = rect
    return (x + w / 2, y + h / 2)


def main() -> int:
    from tokenboard.config import DB_PATH
    from tokenboard.scanner import Scanner
    from tokenboard.store import Store
    from tokenboard.ui import panel as P

    store = Store(DB_PATH)
    p = P.Panel(store, Scanner(store))
    p.create()
    p.show()
    try:
        # ---- 侧栏：四个导航项都要能命中并且切换视图
        for i in range(4):
            r = p._nav_rect(i)
            check(f"侧栏第 {i + 1} 项可命中", p._nav_at(*center(r)) == i,
                  str(p._nav_at(*center(r))))
            p.on_click(*center(r))
            check(f"点第 {i + 1} 项切到视图 {i}", p._view_idx == i, str(p._view_idx))

        # 底部「同步设置」回调
        fired = []
        p.on_open_settings = lambda: fired.append(True)
        p.on_click(*center(p._settings_rect()))
        check("侧栏「同步设置」触发回调", fired == [True])

        # ---- 时间范围（先在非额度视图）
        p.on_click(*center(p._nav_rect(0)))
        for idx in (1, 2, 3, 0):
            x, y, w, h = P.PERIOD_X, P.TOOLBAR_Y + 6, P.PERIOD_W, 22
            p.on_click(x + idx * w + w / 2, y + h / 2)
            check(f"点时间范围第 {idx + 1} 项", p._period_idx == idx,
                  str(p._period_idx))

        # ---- 工具栏按钮
        check("刷新按钮可命中", p._btn_at(*center(p._btn_rect("refresh"))) == "refresh")
        check("同步按钮可命中", p._btn_at(*center(p._btn_rect("sync"))) == "sync")

        # ---- 搜索框
        check("搜索框可命中", p._search_box_at(*center(p._search_rect())))

        # ---- 行展开
        p._load()
        if p._rows:
            i = 0
            rx, ry, rw, rh = p._row_rect(i)
            key = p._rows[i]["key"]
            before = key in p._expanded
            p.on_click(rx + rw / 2, ry + rh / 2)
            check("点主行切换展开状态", (key in p._expanded) != before)
        else:
            check("有可点的行", False, "库里没有数据")

        # ---- 窗口最小尺寸（改版后是 860x560）
        check("最小尺寸合理", p.min_width >= 860 and p.min_height >= 560,
              f"{p.min_width}x{p.min_height}")

        # ---- 缩到最小尺寸不崩
        p.on_size(p.min_width, p.min_height)
        p.invalidate()
        check("最小尺寸下布局不崩", True)
    finally:
        try:
            p.destroy()
        except Exception:  # noqa: BLE001
            pass
        store.close()

    print()
    print(f"通过 {ok_count} 项" + ("" if not failures else f"，失败 {len(failures)} 项：{failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())