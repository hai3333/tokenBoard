"""常驻桌面的小框（桌面挂件）。

设计:
* 240x80 的小卡片，置顶常驻在工作区右下角，不占任务栏。
* 半透明（WS_EX_LAYERED + 整体 alpha）：浮在桌面上像张贴纸，不像块实心板子。
* 配色跟主面板走（中性炭黑 + emerald，同样支持明暗切换）。
* 顶部一条是拖动区（按住能把小框挪走），其余地方点一下展开主面板 ——
  **两边都要**：早前把整块都设成拖动区，结果变成「只能拖不能点」，
  用户明确不要这种挂件。
* 位置记忆在 %LOCALAPPDATA%\\TokenBoard\\widget.json，拖完写回去。
* 数据自己查 SQLite（读并发安全），不依赖主面板是否展开。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from datetime import datetime, timedelta

from ..config import APP_META, WIDGET_STATE_PATH, app_color
from .theme import ACCENT, BASE, LINE_2, SURFACE, TEXT, TEXT_2, TEXT_3, mix
from . import theme as theme_mod
from .win32 import (DT_CENTER as DT_C, DT_LEFT as DT_L, DT_RIGHT as DT_R,
                    DT_SINGLELINE, DT_SINGLELINE as DT_SL,
                    DT_VCENTER as DT_VC, HTCAPTION, HTCLIENT,
                    Canvas, Font, Window, WS_EX_LAYERED, WS_EX_TOOLWINDOW,
                    WS_EX_TOPMOST, WS_PLAIN, user32)

MINI_W = 240
MINI_H = 80
DRAG_H = 26          # 顶部这一条是拖动区
PAD = 12
REFRESH_MS = 1500

# 整窗透明度：255 = 完全不透明。用户嫌它像一块实心板子，压到 210 让桌面透上来。
WINDOW_ALPHA = 210

# 配色：全白（纯白，靠字号/粗细区分层次，不再用别的颜色）
WHITE = "#FFFFFF"

# 颜色点：每家工具一个小点（统一白色）
DOT_R = 3
DOT_GAP = 21


class MiniBar(Window):
    """桌面小框。"""

    def __init__(self, store, on_expand):
        super().__init__("TokenBoard", MINI_W, MINI_H,
                         class_name="TokenBoardMini",
                         style=WS_PLAIN,
                         ex_style=WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_LAYERED)
        # 小框就是 240x80，基类的最小尺寸（620x420）是给主面板用的。
        # 不改的话，窗口创建/拖动时会被最小尺寸钳制撑成一大块底板。
        self.min_width = MINI_W
        self.min_height = MINI_H
        self.store = store
        self.on_expand = on_expand
        self._bg_color = BASE
        self._total = 0
        self._reqs = 0
        self._cost = 0.0
        self._spark: list[float] = []
        self._apps: list[str] = []
        self._top3: list[tuple[str, int]] = []   # 今天用量前三（图标 + Token 数）
        self._hover = False
        self._pos = self._read_state()
        self._saved_pos: tuple[int, int] | None = None   # 已落盘的位置

        self.f_brand = Font(10, 700)
        self.f_num = Font(20, 700, "Consolas")
        self.f_meta = Font(9, 400)
        self.f_tiny = Font(8, 400, "Consolas")

    # ------------------------------------------------------------------
    # 位置记忆
    def _read_state(self) -> tuple[int, int] | None:
        try:
            with open(WIDGET_STATE_PATH, "r", encoding="utf-8") as f:
                st = json.load(f)
            x, y = int(st["x"]), int(st["y"])
            if 0 <= x < 8000 and 0 <= y < 8000:
                return (x, y)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _write_state(self):
        """把当前位置写回 widget.json（位置没变就不重复写）。

        先写临时文件再 os.replace 换过去 —— 直接 open("w") 会**先把文件截断**，
        正好在这瞬间读文件的人会读到空内容（JSON 解析失败 → 位置读成空）。
        替换是原子的，读者要么看到旧值要么看到新值，不会读到半个文件。

        「位置没变就不写」的判断要**顺带看一眼文件**：
        只看内存里的位置的话，文件一旦被删掉/写坏了，
        应用会以为「已经存过了」再也不写，位置就真的丢了。
        """
        try:
            x, y = self.get_pos()
        except Exception:  # noqa: BLE001
            return
        if (x, y) == self._saved_pos and self._state_file_has(x, y):
            return
        self._saved_pos = (x, y)
        try:
            tmp = WIDGET_STATE_PATH.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"x": x, "y": y}, f)
            os.replace(tmp, WIDGET_STATE_PATH)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _state_file_has(x: int, y: int) -> bool:
        """文件里现在记的坐标是不是就是 (x, y)。"""
        try:
            with open(WIDGET_STATE_PATH, "r", encoding="utf-8") as f:
                st = json.load(f)
            return int(st["x"]) == x and int(st["y"]) == y
        except Exception:  # noqa: BLE001
            return False

    def default_pos(self) -> tuple[int, int]:
        """没记住位置时放**主显示器工作区**右下角。

        坑：不能用 GetSystemMetrics(0/1) —— 那是**虚拟屏幕**尺寸（多显示器时
        会比主屏大），算出来的位置会把小框放到屏幕外，右半截看不见
        （表现是卡片右边被切掉、数字显示不全）。
        """
        area = self._work_area()
        w = int(MINI_W * self.scale)
        h = int(MINI_H * self.scale)
        return (area[2] - w - 24, area[3] - h - 24)

    @staticmethod
    def _work_area() -> tuple[int, int, int, int]:
        """主显示器工作区 (left, top, right, bottom)，拿不到就退回屏幕尺寸。"""
        try:
            SPI_GETWORKAREA = 0x0030
            rect = wintypes.RECT()
            if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0,
                                            ctypes.byref(rect), 0):
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:  # noqa: BLE001
            pass
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        return (0, 0, sw, sh)

    def create(self):
        super().create()
        # 整窗半透明：底板透出桌面，不再是一块实心深色板子
        self.set_layered_alpha(WINDOW_ALPHA)
        pos = self._pos or self.default_pos()
        pos = self._clamp_to_screen(pos)
        self.move_to(*pos)
        self.set_topmost(True)

    def _window_size(self) -> tuple[int, int]:
        """小框当前的客户区尺寸（物理像素）。"""
        if not self.hwnd:
            return (int(MINI_W * self.scale), int(MINI_H * self.scale))
        cr = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(cr))
        return (cr.right, cr.bottom)

    def _clamp_to_screen(self, pos: tuple[int, int]) -> tuple[int, int]:
        """把位置拉回工作区内，保证小框完整可见。"""
        x, y = pos
        area = self._work_area()
        w, h = self._window_size()
        x = max(area[0], min(x, area[2] - w))
        y = max(area[1], min(y, area[3] - h))
        return (x, y)

    # ------------------------------------------------------------------
    # 数据
    def start(self):
        self.create()
        self.set_timer(REFRESH_MS, 1)
        self._load()
        self.show()
        self.set_topmost(True)

    def _load(self):
        """查今天的总量/请求数/成本 + 近 30 天每日消耗。"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            since = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
            rows = self.store.summary(since_day=today)
            self._total = sum(r["total_tokens"] or 0 for r in rows)
            self._reqs = sum(r["requests"] or 0 for r in rows)
            self._cost = sum(r["cost_usd"] or 0.0 for r in rows)
            self._apps = [r["app"] for r in rows
                          if (r["total_tokens"] or 0) > 0]
            if not self._apps:
                self._apps = list(APP_META.keys())
            self._top3 = sorted(
                ((r["app"], int(r["total_tokens"] or 0)) for r in rows),
                key=lambda t: -t[1])[:3]

            per_day: dict[str, float] = {}
            for r in self.store.daily(since_day=since):
                per_day[r["day"]] = per_day.get(r["day"], 0.0) + \
                    (r["total_tokens"] or 0)
            out = []
            for i in range(29, -1, -1):
                d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                out.append(per_day.get(d, 0.0))
            self._spark = out
        except Exception:  # noqa: BLE001
            # 读库失败就沿用上一次的数据，别让小框变空
            pass

    def on_timer(self, tid: int):
        if tid == 1:
            self._load()
            self.invalidate()
            # 位置落盘兜底：除了拖完（WM_EXITSIZEMOVE），
            # 任何位置变化（托盘隐藏再显示、程序化移动）最多 1.5 秒写一次。
            self._write_state()

    # ------------------------------------------------------------------
    # 绘制（中性炭黑 + emerald，和主面板同一套）
    def draw(self, c: Canvas):
        c.fill(BASE)
        card = SURFACE if not self._hover else mix(SURFACE, "#FFFFFF", 0.06)
        c.round_rect(0, 0, MINI_W, MINI_H, 10, fill=card,
                     stroke=LINE_2, stroke_w=1.0)

        # 品牌标记：三根递增的柱（emerald，和托盘图标同一套形状）
        for i, bh in enumerate((5, 8, 12)):
            c.round_rect(PAD + i * 5, 18 - bh, 3, bh, 1.5, fill=ACCENT)
        c.text(PAD + 20, 6, 120, 16, "TokenBoard", self.f_brand, TEXT,
               align=DT_L | DT_VC | DT_SL)

        # 今天总量（右对齐，大号数字）
        c.text(MINI_W - PAD - 140, 2, 140, 24, fmt_compact(self._total),
               self.f_num, TEXT, align=DT_R | DT_VC | DT_SL)

        # 今天 · N 次请求 · 成本；悬停时换成今天 top3 工具速览
        if self._hover and self._top3:
            tx = PAD
            for app, tk in self._top3:
                c.ellipse(tx, 30, 5, 5, fill=app_color(app))
                icon = APP_META.get(app, {}).get("icon", "?")
                txt = f"{icon} {fmt_compact(tk)}"
                tw, _ = c.measure(txt, self.f_tiny)
                c.text(tx + 8, 24, tw + 2, 14, txt, self.f_tiny, TEXT_2,
                       align=DT_L | DT_VC | DT_SL)
                tx += 8 + tw + 12
        else:
            money = fmt_mini_money(self._cost)
            c.text(PAD, 24, MINI_W - PAD * 2 - 14, 14,
                   f"今天 · {self._reqs:,} 次 · {money}", self.f_meta, TEXT_3,
                   align=DT_L | DT_VC | DT_SL)

        # 近 30 天迷你趋势（emerald）
        self._draw_spark(c, PAD, 42, MINI_W - PAD * 2, 18)

        # 工具圆点：用各家的品牌色，和列表图标块同一套识别色
        for i, app in enumerate(self._apps[:8]):
            cx = PAD + i * DOT_GAP
            c.ellipse(cx, MINI_H - 14, DOT_R * 2, DOT_R * 2, fill=app_color(app))

        # 右侧小箭头：提示「点一下能展开主面板」
        cx = MINI_W - PAD - 6
        cy = 31
        c.polyline([(cx - 3, cy - 4), (cx + 1, cy), (cx - 3, cy + 4)],
                   TEXT_3, 1.2)

    def _draw_spark(self, c: Canvas, x, y, w, h):
        vals = self._spark
        if not vals or max(vals) <= 0:
            c.text(x, y, w, h, "暂无数据", self.f_meta, TEXT_3,
                   align=DT_C | DT_VC | DT_SL)
            return
        n = len(vals)
        mx = max(vals)
        base = y + h
        pts = []
        for i, v in enumerate(vals):
            px = x + w * i / (n - 1)
            py = base - (h - 2) * (v / mx)
            pts.append((px, py))
        # 面积（深色界面没有 alpha 通道，用一条一条的横带逼近渐变）
        top = min(p[1] for p in pts)
        span = max(1.0, base - top)
        for row in range(int(span) + 1):
            yb = base - row
            xs = [p[0] for p in pts if p[1] <= yb]
            if not xs:
                break
            t = row / span
            c.fill_rect(min(xs), yb, max(1.0, max(xs) - min(xs)), 1,
                        mix(SURFACE, ACCENT, 0.30 * (1 - t) ** 1.5))
        c.polyline(pts, ACCENT, 1.4)
        c.ellipse(pts[-1][0] - 2, pts[-1][1] - 2, 4, 4, ACCENT)

    # ------------------------------------------------------------------
    # 交互：顶部一条拖动区，其余点击展开主面板
    def on_nc_hit_test(self, x: float, y: float) -> int:
        """顶部一条是拖动区，其余是点击区。

        两边都要：按住顶部能把小框挪走，
        点其它地方能展开主面板（早前整块都设成拖动区，
        结果点不动了，用户不要这种「只剩拖动」的挂件）。
        """
        if 0 <= y < DRAG_H:
            return HTCAPTION
        return HTCLIENT

    def on_click(self, x: float, y: float):
        """点一下展开主面板。"""
        self.on_expand()

    def on_hover(self):
        pass

    def on_mousemove(self, x: float, y: float):
        inside = 0 <= x < MINI_W and 0 <= y < MINI_H
        if inside != self._hover:
            self._hover = inside
            self.invalidate()

    def on_mouseleave(self):
        # Windows 只在鼠标「进入」时发消息，移出去要靠 WM_MOUSELEAVE，
        # 不然小框的悬停高亮会一直卡住。
        if self._hover:
            self._hover = False
            self.invalidate()

    # ------------------------------------------------------------------ 外观
    def apply_theme(self, pref: str) -> None:
        theme_mod.apply(pref)
        self._bg_color = BASE
        self.invalidate()

    def on_setting_change(self) -> None:
        if theme_mod.resolve("auto") != theme_mod.MODE:
            self.apply_theme("auto")

    def on_moved(self):
        """拖完：记住位置，并把它拉回工作区。

        拖到屏幕外就再也找不着了（托盘菜单只能显示/隐藏，没法定位），
        所以松手时统一回夹一次。
        """
        self._write_state()
        x, y = self.get_pos()
        nx, ny = self._clamp_to_screen((x, y))
        if (nx, ny) != (x, y):
            self.move_to(nx, ny)
            self._write_state()


def fmt_compact(n: int) -> str:
    """和大面板一致的紧凑数字：283.6M / 15.4K。"""
    n = float(n or 0)
    for unit, div in (("T", 1e12), ("G", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= div:
            v = n / div
            return f"{v:.1f}{unit}" if v < 100 else f"{v:.0f}{unit}"
    return f"{n:.0f}"


def fmt_mini_money(usd: float) -> str:
    """小框里的金额：$2.17 / $73.2 / $1.53K。"""
    v = float(usd or 0)
    if v >= 1000:
        return f"${v / 1000:.2f}K"
    if v >= 100:
        return f"${v:.0f}"
    if v >= 1:
        return f"${v:.2f}"
    if v > 0:
        return f"${v:.3f}"
    return "$0"


theme_mod.register(sys.modules[__name__])

