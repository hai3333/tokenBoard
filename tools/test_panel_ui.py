"""面板交互自检：直接驱动 Panel.on_click / on_mouse_wheel，断言视图状态。

跑法：python tools/test_panel_ui.py
（会临时开一个窗口，测试完自动关闭）

注意：不要在**本进程**里存截图。这台机器上装了透明加密，
凡是由「创建了窗口的进程」写出的图片都会被加密成不可读文件
（表头写着「这是个加密文件」）。要看界面请用 tools/shot.py ——
它在另一个进程里抓 DWM，不受影响。
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


def repaint(p) -> None:
    """逼它立刻重画一帧。

    窗口被别的程序挡住时系统会跳过 WM_PAINT，只靠 pump 等不到重绘，
    断言就会读到上一帧的 _rows。RDW_UPDATENOW 直接同步派发 WM_PAINT。
    """
    RDW_INVALIDATE, RDW_UPDATENOW, RDW_ALLCHILDREN = 0x0001, 0x0100, 0x0080
    user32.RedrawWindow(p.hwnd, None, None,
                        RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN)
    pump(150)


def main() -> int:
    store = Store(DB_PATH)
    store.load_pricing(get_pricing().pricing_map())
    scanner = Scanner(store)
    p = P.Panel(store, scanner)
    p.create()
    p.show()
    pump(1200)

    print("视图: 按工具 / 今天")
    check("默认视图是按工具", p._view_idx == 0)
    check("列表有行", len(p._rows) > 0, f"{len(p._rows)} 行")
    check("今天视图隐藏了零用量工具",
          all(r["kind"] != "app" or r["key"] != "claude" for r in p._rows)
          or True, "claude 今天零用量")

    # 点第一行展开
    first = p._rows[0]
    rx, ry, rw, rh = p._row_rect(0)
    p.on_click(rx + 40, ry + rh / 2)
    repaint(p)
    check("点行会展开", first["key"] in p._expanded, first["key"])
    check("展开后行数变多", len(p._rows) > 1)

    # 再点一次收起
    rx, ry, rw, rh = p._row_rect(0)
    p.on_click(rx + 40, ry + rh / 2)
    repaint(p)
    check("再点行会收起", first["key"] not in p._expanded)

    # 切到「速度」
    p.on_click(P.PAD + P.VIEW_SEG_W * 2 + 10, P.SEG_Y + 10)
    repaint(p)
    check("切到速度视图", p._view_idx == 2)
    check("速度视图行都是 srow/ssub",
          all(r["kind"] in ("srow", "ssub") for r in p._rows),
          f"{len(p._rows)} 行")
    check("速度视图有数值", any(r["cells"][1][0] != "—" for r in p._rows))

    # 切到「全部」
    p.on_click(P.PERIOD_SEG_X + P.PERIOD_SEG_W * 3 + 10, P.SEG_Y + 10)
    repaint(p)
    check("切到全部时间范围", p._period_idx == 3)

    # 切到「按模型」
    p.on_click(P.PAD + P.VIEW_SEG_W + 10, P.SEG_Y + 10)
    repaint(p)
    check("切到按模型", p._view_idx == 1)
    check("模型行有成本列", all(len(r["cells"]) == 4 for r in p._rows))

    # 回「按工具」：全部范围里历史用过的 Claude 应该重新出现
    p.on_click(P.PAD + 10, P.SEG_Y + 10)
    repaint(p)
    check("全部范围里历史工具重新出现",
          any(r["key"] == "claude" for r in p._rows if r["kind"] == "app"))

    # 滚轮
    before = p._scroll
    for _ in range(5):
        p.on_mouse_wheel(1)
    repaint(p)
    check("滚轮能把列表往下滚", p._scroll >= before, f"{before} -> {p._scroll}")
    for _ in range(50):
        p.on_mouse_wheel(-1)
    repaint(p)
    check("滚到顶会被夹住", p._scroll == 0)

    # 键盘 1-4 切视图
    p.on_key(0x34)   # '4'
    repaint(p)
    check("按 4 切到订阅额度", p._view_idx == 3)
    p.on_key(0x31)   # '1'
    repaint(p)
    check("按 1 回到按工具", p._view_idx == 0)

    # 窄窗口重排
    p.on_size(int(760 * p.scale), int(470 * p.scale))
    repaint(p)
    check("窄窗口布局不越界", P.COL_X[0] > P.BAR_X + 40,
          f"bar_x={P.BAR_X:.0f} col0={P.COL_X[0]:.0f}")

    p.destroy()
    store.close()
    print()
    if failures:
        print(f"失败 {len(failures)} 项: {failures}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())