"""主面板 —— 原生 Win32 + GDI 绘制。

布局（整宽两段式：上面指标、下面明细）

    TokenBoard                                          ─  ×
    [按工具][按模型][速度][订阅额度]      [今天|7天|30天|全部]
    ┌ 总消耗 ─────────┐ ┌ 成本 ─┐ ┌ 首字 ─┐ ┌ 输出速度 ┐
    │ 24.5M      ╱╲~~ │ │$3.42  │ │ 8.9s  │ │ 62 t/s   │
    │ 今天·284 次请求  │ │≈¥24.6 │ │P90 39s│ │输出 1.2M │
    └─────────────────┘ └───────┘ └───────┘ └──────────┘
      工具/模型            TOKEN    成本    首字    tok/s
    ▶ Codex               3.7M    $2.10    1.2s     45
      主力 gpt-6.1-sol
    （本期没用过的工具不占位置，只在底部状态条留个灯）

为什么要改：
* 原来左边一张大卡片吃掉四分之一宽度，右边列表只剩 6 个数字位；
  现在指标压成顶部一排四块，列表拿到整宽，token / 成本 / 首字 / 速度同屏。
* 成本、首字、吞吐原来完全没有入口，现在既是顶部 KPI，也是每一行的列。
* 「速度」单独一屏：按模型排，先看谁首字快、谁吐字快。
"""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
import time
from ctypes import wintypes
from datetime import datetime, timedelta

from ..config import APP_META, CNY_RATE, app_color, app_label
from ..scanner import Scanner, trim_working_set
from ..store import Store
from .. import sync as syncmod
from .theme import (ACCENT, BASE, COST, DANGER, FONT_NUM, LATENCY, LINE, LINE_2,
                    SPEED, SURFACE, SURFACE_2, SURFACE_3, TEXT, TEXT_2,
                    TEXT_3, WARN, mix, tint)
from .win32 import (HTCLIENT, HTCAPTION, Canvas, Font, Window, user32)

# ---------------------------------------------------------------- 材质细节
# 深色界面没有投影和 alpha，层次只能靠「一像素」堆出来：
# 卡片 = 投影 + 面 + 1px 描边 + 顶边高光；列表 = 分隔线 + 悬停整行底色。
CARD_LINE = "#28374F"      # 卡片描边（蓝一档，勾出边界但不死板）
CARD_TOP = "#243149"       # 卡片顶边高光（模拟受光）
SHADOW = "#070B13"         # 卡片投影（比底色深）
ROW_HOVER = "#1B2739"      # 行悬停底色
TRACK = "#1B2434"          # 进度条轨道（中性兜底，行内会按品牌色再染一次）
GRID = "#1C2536"           # 图表网格线

# ---------------------------------------------------------------- 基础尺寸
WIN_W = 880            # 当前客户区尺寸（设计像素），随窗口缩放变化
WIN_H = 520
TITLE_H = 32           # 自绘标题栏高度（系统标题栏已去掉）

PAD = 16
HEAD_H = 44            # 顶部控件条
SEG_H = 24
SEG_Y = TITLE_H + 10
VIEW_SEG_W = 58
PERIOD_SEG_W = 52

KPI_Y = TITLE_H + HEAD_H + 14       # 90
KPI_H = 88
KPI_GAP = 10

COL_HEAD_Y = KPI_Y + KPI_H + 12     # 190
COL_HEAD_H = 16
BODY_Y = COL_HEAD_Y + COL_HEAD_H + 4   # 210

FOOT_H = 34
FOOT_Y = WIN_H - FOOT_H

# ---------------------------------------------------------------- 行尺寸
ROW_MAIN = 44          # 工具行 / 模型行（名称 + 副标题两行）
ROW_SUB = 26           # 展开后的子行

TICK_W = 3
NAME_W = 168

# 右侧四个数值列（从右往左排）
COL_W = (66, 74, 62, 66)     # token / 成本 / 首字 / 速度
COL_GAP = 10

# 自绘标题栏按钮
TB_BTN_W = 40
TB_BTN_H = TITLE_H

# 订阅额度视图
QUOTA_GAP = 10
QUOTA_STEP = 40
# 额度环也走白色系（原来是按 provider 分品牌色），层次交给「已用比例」本身
QUOTA_COLOR = {
    "minimax": "#FFFFFF",
    "codex": "#FFFFFF",
    "volcengine": "#FFFFFF",
}

# ---------------------------------------------------------------- 派生布局
# 下面这些由 _relayout() 按当前窗口尺寸重算。绘制代码直接读模块变量，
# 所以统一在 _relayout() 里用 global 刷新一次（改动面最小）。
BODY_H = 270
COL_X = [0, 0, 0, 0]
KPI_X = [0, 0, 0, 0]
KPI_W = [0, 0, 0, 0]
PERIOD_SEG_X = 0
BAR_X = 0
BAR_W = 0
NAME_X = 0
BAR_END = 0
SCROLL_X = 0
QUOTA_W = 0
QUOTA_Y = 0
QUOTA_H = 0
TB_MIN_X = 0
TB_CLOSE_X = 0


def _relayout(w: float, h: float) -> None:
    """窗口尺寸变了就重算所有派生布局常量（单位：设计像素）。"""
    global WIN_W, WIN_H, BODY_H, FOOT_Y, COL_X, KPI_X, KPI_W, PERIOD_SEG_X, \
        BAR_X, BAR_W, NAME_X, BAR_END, SCROLL_X, QUOTA_W, QUOTA_Y, QUOTA_H, \
        TB_MIN_X, TB_CLOSE_X

    WIN_W = w
    WIN_H = h
    FOOT_Y = h - FOOT_H
    BODY_H = max(80, FOOT_Y - 8 - BODY_Y)

    # 额度视图没有指标卡，卡片直接从控件条下面开始，别在顶上留一块空洞
    QUOTA_Y = TITLE_H + HEAD_H + 12
    QUOTA_H = max(80, FOOT_Y - 10 - QUOTA_Y)

    # 数值列：右对齐，从右边缘往回排
    right = w - PAD
    x = right
    col_x = [0, 0, 0, 0]
    for i in range(3, -1, -1):
        x -= COL_W[i]
        col_x[i] = x
        x -= COL_GAP
    COL_X = col_x
    BAR_END = COL_X[0] - 12

    NAME_X = PAD + 28
    BAR_X = NAME_X + NAME_W + 10
    BAR_W = max(48, BAR_END - BAR_X)
    SCROLL_X = w - PAD + 2

    # 指标卡：总消耗占大头（里面有趋势线），其余三等分
    total = w - PAD * 2 - KPI_GAP * 3
    w0 = max(200.0, total * 0.36)
    rest = (total - w0) / 3
    KPI_X[0] = PAD
    KPI_W[0] = w0
    for i in range(1, 4):
        KPI_X[i] = KPI_X[i - 1] + KPI_W[i - 1] + KPI_GAP
        KPI_W[i] = rest

    PERIOD_SEG_X = w - PAD - PERIOD_SEG_W * 4
    QUOTA_W = w - PAD * 2 - 12

    TB_MIN_X = w - TB_BTN_W * 2
    TB_CLOSE_X = w - TB_BTN_W


# 初始尺寸算一遍
_relayout(WIN_W, WIN_H)

VIEWS = [("按工具", "app"), ("按模型", "model"), ("速度", "speed"),
         ("订阅额度", "quota")]
PERIODS = [("今天", 0), ("7 天", 7), ("30 天", 30), ("全部", None)]

# 每种视图的列顺序（4 列）
VIEW_COLS = {
    0: ("TOKEN", "成本", "首字", "tok/s"),
    1: ("TOKEN", "成本", "首字", "tok/s"),
    2: ("首字", "tok/s", "输出", "样本"),
}

WINDOW_LABEL = {"5h": "5 小时限额", "weekly": "周限额"}

log = logging.getLogger("tokenboard")

DISCLOSURE_CLOSED = "▶"
DISCLOSURE_OPEN = "▼"

# DrawText 对齐标志
DT_L = 0x00000000
DT_C = 0x00000001
DT_R = 0x00000002
DT_VC = 0x00000004
DT_SL = 0x00000020


# ---------------------------------------------------------------- 格式化
def fmt_tokens(n: float) -> str:
    n = float(n or 0)
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return f"{int(n)}"


def fmt_money(usd: float) -> str:
    """美元金额：一分钱以下也别显示成 0。"""
    v = float(usd or 0)
    if v >= 1000:
        return f"${v / 1000:.2f}K"
    if v >= 100:
        return f"${v:.0f}"
    if v >= 10:
        return f"${v:.1f}"
    if v >= 1:
        return f"${v:.2f}"
    if v > 0:
        return f"${v:.3f}"
    return "$0"


def fmt_cny(usd: float) -> str:
    """人民币参考值：上万用「万」，别把 ¥11,054.79 这种长串塞进小卡片。"""
    v = float(usd or 0) * CNY_RATE
    if v >= 10_000:
        return f"¥{v / 10_000:.2f}万"
    if v >= 1000:
        return f"¥{v:,.0f}"
    if v >= 10:
        return f"¥{v:.1f}"
    return f"¥{v:.2f}"


def fmt_ms(ms: float) -> str:
    """耗时：<1s 用 ms，<1min 用 s，再长用 m。"""
    v = float(ms or 0)
    if v <= 0:
        return "—"
    if v < 1000:
        return f"{v:.0f}ms"
    if v < 60_000:
        return f"{v / 1000:.1f}s"
    return f"{v / 60_000:.1f}m"


def fmt_tps(v: float) -> str:
    v = float(v or 0)
    return f"{v:.0f}" if v > 0 else "—"


def fmt_until(ms: int) -> str:
    """把重置时间戳说成「还有多久」，比绝对时间好读得多。"""
    if not ms:
        return "-"
    sec = int(ms / 1000 - time.time())
    if sec <= 0:
        return "即将重置"
    d, rem = divmod(sec, 86400)
    h, rem2 = divmod(rem, 3600)
    m = rem2 // 60
    if d:
        return f"{d} 天 {h} 小时后"
    if h:
        return f"{h} 小时 {m} 分后"
    return f"{m} 分钟后"


class Panel(Window):
    """TokenBoard 主窗口。"""

    def __init__(self, store: Store, scanner: Scanner):
        super().__init__("TokenBoard", WIN_W, WIN_H)
        self._bg_color = BASE
        self.store = store
        self.scanner = scanner
        self.min_width = 720
        self.min_height = 460

        self._period_idx = 0
        # 启动时默认选某个时间范围（TOKENBOARD_PERIOD=all|7|30|today）
        _alias = {"all": 3, "全部": 3, "7": 1, "7d": 1, "30": 2, "30d": 2,
                  "today": 0, "今天": 0}
        _pp = os.environ.get("TOKENBOARD_PERIOD", "").strip().lower()
        if _pp in _alias:
            self._period_idx = _alias[_pp]
        # 0=按工具 1=按模型 2=速度 3=订阅额度
        _v = os.environ.get("TOKENBOARD_VIEW", "").strip().lower()
        self._view_idx = {"quota": 3, "model": 1, "speed": 2}.get(_v, 0)
        self._expanded: set[str] = set()     # 展开的主行 key
        _pre = os.environ.get("TOKENBOARD_EXPAND")
        if _pre:
            self._expanded.add(_pre.lower())
        self._scroll = 0
        self._quota_scroll = 0      # 额度视图独立滚动（像素单位）
        self._q: queue.Queue = queue.Queue()
        self._scanning = False
        self._trim_pending = False
        self._status: dict[str, tuple[bool, str]] = {}
        self._status_error = ""
        self._last_update = "—"
        self._rows: list[dict] = []
        self._row_y: list[float] = []
        self._content_h = 0
        self._totals: dict = {}
        self._speed: dict = {}
        self._quota: list[dict] = []
        self._quota_cache: dict[str, dict] = {}
        self._spark: list[float] = []
        self._hover_row = -1
        self._hover_tb = ""
        self._pressed_tb = ""
        self._dot_hit: list[tuple[str, float, float, float]] = []
        self._ctx_row = -1          # 右键菜单目标行
        self._ctx_x = 0.0
        self._ctx_y = 0.0
        self._ctx_items: list[tuple[str, str]] = []   # [(id, label), ...]
        self._ctx_hot = -1          # 菜单项悬停索引
        self._search_q = ""         # 搜索关键字
        self._search_focus = False
        # ---- 云同步状态（面板只负责定时触发与展示，网络动作在后台线程）
        self._sync_cfg = None
        self._syncing = False
        self._sync_note = ""
        self._sync_failed = False
        self.sync_win = None        # 设置窗口（由 app.py 懒创建）
        self.on_sync_settings_request = None   # 主线程里真正去建窗口的回调
        self._pending_sync_win = False         # IPC 线程只置这个布尔
        self.tray = None

        self.f_title_s = Font(10, 700)
        self.f_seg = Font(10, 400)
        self.f_seg_sel = Font(10, 700)
        self.f_kpi_label = Font(9, 400)
        self.f_kpi = Font(24, 700, FONT_NUM)
        self.f_kpi_m = Font(20, 700, FONT_NUM)
        self.f_kpi_unit = Font(10, 400, FONT_NUM)
        self.f_kpi_sub = Font(8, 400)
        self.f_head = Font(8, 400)
        self.f_name = Font(11, 700)
        self.f_name_sub = Font(8, 400)
        self.f_cell = Font(10, 700, FONT_NUM)
        self.f_numb = Font(10, 700, FONT_NUM)
        self.f_cell_s = Font(9, 700, FONT_NUM)
        self.f_cell_sub = Font(9, 400, FONT_NUM)
        self.f_meta = Font(9, 400)
        self.f_small = Font(9, 400)
        self.f_tiny = Font(8, 400)
        self.f_tinyb = Font(8, 700, FONT_NUM)
        self.f_foot = Font(9, 400)
        self.f_gauge = Font(13, 700, FONT_NUM)

    # ------------------------------------------------------------------
    def start(self):
        self.create()
        self.set_timer(500, 1)          # 刷新界面
        self.set_timer(60_000, 2)      # 触发扫描
        self.set_timer(300_000, 3)     # 刷新订阅额度（5 分钟一次，别太频繁打接口）
        self.set_timer(60_000, 4)      # 检查云同步是否到点
        self._start_scan()
        self._start_quota()
        self.reload_sync()
        self.show()

    # ------------------------------------------------------------- 数据
    def _since_day(self) -> str | None:
        days = PERIODS[self._period_idx][1]
        if days is None:
            return None
        if days == 0:
            return datetime.now().strftime("%Y-%m-%d")
        return (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    def _load(self) -> None:
        since = self._since_day()
        rows = self.store.summary(since_day=since)
        by_app = {r["app"]: r for r in rows}

        self._totals = {
            "total": sum(r["total_tokens"] or 0 for r in rows),
            "reqs": sum(r["requests"] or 0 for r in rows),
            "input": sum(r["input_tokens"] or 0 for r in rows),
            "output": sum(r["output_tokens"] or 0 for r in rows),
            "cache": sum(r["cache_read_tokens"] or 0 for r in rows),
            "cost": sum(r["cost_usd"] or 0.0 for r in rows),
        }
        self._speed = self.store.speed_stats(since_day=since)

        if self._view_idx == 0:
            self._build_app_rows(by_app)
        elif self._view_idx == 1:
            self._build_model_rows()
        elif self._view_idx == 2:
            self._build_speed_rows()
        self._apply_search_filter()
        self._layout_rows()
        if self._view_idx != 3:
            self._spark = self._load_spark()

    def _apply_search_filter(self) -> None:
        """搜索：主行命中或子行命中则保留父行；子行只留命中的。"""
        q = self._search_q.strip().lower()
        if not q:
            return

        def match(r):
            return any(q in str(r.get(f, "") or "").lower()
                       for f in ("name", "sub", "key"))

        kept = []
        rows = self._rows
        i = 0
        while i < len(rows):
            r = rows[i]
            if r["kind"] in ("sub", "ssub"):
                i += 1
                continue
            children = []
            j = i + 1
            while j < len(rows) and rows[j]["kind"] in ("sub", "ssub"):
                children.append(rows[j])
                j += 1
            if match(r):
                kept.append(r)
                kept.extend(children)
            else:
                matched = [c for c in children if match(c)]
                if matched:
                    kept.append(r)
                    kept.extend(matched)
            i = j
        self._rows = kept

    def _load_spark(self) -> list[float]:
        """近 30 天每天的总消耗（给指标卡里的趋势线用，缺的日子补 0）。"""
        try:
            since = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
            rows = self.store.daily(since_day=since)
        except Exception:  # noqa: BLE001
            return []
        per_day: dict[str, float] = {}
        for r in rows:
            per_day[r["day"]] = per_day.get(r["day"], 0.0) + (r["total_tokens"] or 0)
        today = datetime.now()
        return [per_day.get((today - timedelta(days=i)).strftime("%Y-%m-%d"), 0.0)
                for i in range(29, -1, -1)]

    # ---- 速度取值着色：拿不到数据的列用弱色，别让人误以为是 0 ----
    @staticmethod
    def _cell(text: str, has: bool, strong: bool = True) -> tuple[str, str]:
        if has:
            return (text, TEXT if strong else TEXT_2)
        return (text, TEXT_3)

    # ---- 按工具：可展开到该工具的模型 ------------------------------------
    def _build_app_rows(self, by_app: dict) -> None:
        since = self._since_day()
        per_app = self.store.models_by_app(since_day=since)
        speed = self._speed or {}
        self._rows = []

        # 本期没用过的工具（比如已经不用的 Claude Code）不占位置
        apps = [a for a in APP_META if (by_app.get(a) or {}).get("total_tokens")]
        apps.sort(key=lambda a: -(by_app[a]["total_tokens"] or 0))
        max_t = max((by_app[a]["total_tokens"] or 0 for a in apps), default=0) or 1

        for app in apps:
            r = by_app[app]
            tokens = r["total_tokens"] or 0
            cost = r["cost_usd"] or 0.0
            sp = (speed.get("apps") or {}).get(app) or {}
            models = per_app.get(app) or []
            open_ = app in self._expanded
            sub = (f"主力 {models[0]['name']}" if models
                   else f"{r['requests']:,} 次请求")

            self._rows.append({
                "kind": "app", "key": app,
                "name": APP_META[app].get("short", app_label(app)),
                "sub": sub, "color": app_color(app), "open": open_,
                "bar": tokens / max_t,
                "cells": [
                    self._cell(fmt_tokens(tokens), True),
                    self._cell(fmt_money(cost), True),
                    self._cell(fmt_ms(sp.get("ttft_p50")),
                               bool(sp.get("n_ttft"))),
                    self._cell(fmt_tps(sp.get("tps")), bool(sp.get("tps"))),
                ],
            })
            if not open_:
                continue
            for m in models:
                pm = (speed.get("pairs") or {}).get((app, m["key"])) or {}
                self._rows.append({
                    "kind": "sub", "key": app, "name": m["name"],
                    "color": app_color(app),
                    "bar": (m["tokens"] or 0) / max_t,
                    "cells": [
                        self._cell(fmt_tokens(m["tokens"]), True),
                        self._cell(fmt_money(m.get("cost") or 0), True),
                        self._cell(fmt_ms(pm.get("ttft_p50")),
                                   bool(pm.get("n_ttft"))),
                        self._cell(fmt_tps(pm.get("tps")), bool(pm.get("tps"))),
                    ],
                })

    # ---- 按模型：可展开到用过它的工具 ------------------------------------
    def _build_model_rows(self) -> None:
        since = self._since_day()
        models = self.store.models_aggregated(since_day=since)
        per_model = self.store.apps_by_model(since_day=since)
        speed = self._speed or {}
        self._rows = []
        max_t = max((m["total_tokens"] for m in models), default=0) or 1

        for m in models:
            key = m["key"]
            sp = (speed.get("models") or {}).get(key) or {}
            apps = per_model.get(key) or []
            open_ = key in self._expanded
            sub = (f"主要在 {app_label(apps[0]['app'])}" if apps
                   else f"{m['requests']:,} 次请求")
            self._rows.append({
                "kind": "model", "key": key, "name": m["name"],
                "sub": sub, "color": app_color(m["app"]), "open": open_,
                "bar": (m["total_tokens"] or 0) / max_t,
                "cells": [
                    self._cell(fmt_tokens(m["total_tokens"]), True),
                    self._cell(fmt_money(m["cost_usd"]), True),
                    self._cell(fmt_ms(sp.get("ttft_p50")),
                               bool(sp.get("n_ttft"))),
                    self._cell(fmt_tps(sp.get("tps")), bool(sp.get("tps"))),
                ],
            })
            if not open_:
                continue
            for a in apps:
                pm = (speed.get("pairs") or {}).get((a["app"], key)) or {}
                self._rows.append({
                    "kind": "sub", "key": key, "name": app_label(a["app"]),
                    "color": app_color(a["app"]),
                    "bar": (a["tokens"] or 0) / max_t,
                    "cells": [
                        self._cell(fmt_tokens(a["tokens"]), True),
                        self._cell(fmt_money(a.get("cost") or 0), True),
                        self._cell(fmt_ms(pm.get("ttft_p50")),
                                   bool(pm.get("n_ttft"))),
                        self._cell(fmt_tps(pm.get("tps")), bool(pm.get("tps"))),
                    ],
                })

    # ---- 速度：按模型排，谁首字快 / 谁吐字快 ----------------------------
    def _build_speed_rows(self) -> None:
        since = self._since_day()
        models = self.store.models_aggregated(since_day=since)
        per_model = self.store.apps_by_model(since_day=since)
        speed = self._speed or {}
        pairs = speed.get("pairs") or {}
        self._rows = []

        # 速度按「模型」聚合时是跨工具的，所以这一屏的副标题要写
        # **谁提供了这些采样**，而不是「这个模型用得最多的工具」——
        # 否则会出现「MiniMax Code · 68 次采样」却带着 97 tok/s 的怪事
        # （MiniMax 根本没有耗时字段，那些采样其实来自别的工具）。
        src_by_key: dict[str, list[tuple[str, dict]]] = {}
        for (app, key), pm in pairs.items():
            if pm.get("n"):
                src_by_key.setdefault(key, []).append((app, pm))

        items = []
        for m in models:
            sp = (speed.get("models") or {}).get(m["key"]) or {}
            if not sp or (not sp.get("n_ttft") and not sp.get("tps")):
                continue
            items.append((m, sp))
        # 有吞吐的按吞吐排前面，只有首字的按首字快慢接在后面
        items.sort(key=lambda it: (0 if it[1].get("tps") else 1,
                                   -(it[1].get("tps") or 0),
                                   it[1].get("ttft_p50") or 9e9))
        max_tps = max((it[1].get("tps") or 0 for it in items), default=0) or 1

        for m, sp in items:
            key = m["key"]
            open_ = key in self._expanded
            n = sp.get("n_ttft") or sp.get("n") or 0
            srcs = sorted(src_by_key.get(key) or [],
                          key=lambda kv: -(kv[1].get("n") or 0))
            src_txt = " / ".join(app_label(a) for a, _ in srcs[:2]) or app_label(m["app"])
            self._rows.append({
                "kind": "srow", "key": key, "name": m["name"],
                "sub": f"{src_txt} · {n:,} 次采样",
                "color": app_color(srcs[0][0] if srcs else m["app"]),
                "open": open_,
                "bar": (sp.get("tps") or 0) / max_tps,
                "cells": [
                    self._cell(fmt_ms(sp.get("ttft_p50")),
                               bool(sp.get("n_ttft"))),
                    self._cell(fmt_tps(sp.get("tps")), bool(sp.get("tps"))),
                    self._cell(fmt_tokens(sp.get("out")) if sp.get("out")
                               else "—", bool(sp.get("out"))),
                    self._cell(f"{n:,}", bool(n), strong=False),
                ],
            })
            if not open_:
                continue
            for a in per_model.get(key) or []:
                pm = pairs.get((a["app"], key)) or {}
                if not pm:
                    continue
                nn = pm.get("n_ttft") or pm.get("n") or 0
                self._rows.append({
                    "kind": "ssub", "key": key, "name": app_label(a["app"]),
                    "color": app_color(a["app"]),
                    "bar": (pm.get("tps") or 0) / max_tps,
                    "cells": [
                        self._cell(fmt_ms(pm.get("ttft_p50")),
                                   bool(pm.get("n_ttft"))),
                        self._cell(fmt_tps(pm.get("tps")),
                                   bool(pm.get("tps"))),
                        self._cell(fmt_tokens(pm.get("out")) if pm.get("out")
                                   else "—", bool(pm.get("out"))),
                        self._cell(f"{nn:,}", bool(nn), strong=False),
                    ],
                })

    # ---- 后台任务 ------------------------------------------------------
    def _start_scan(self):
        if self._scanning:
            return
        self._scanning = True

        def work():
            try:
                results = self.scanner.scan()
                self._q.put(("scan_done", results))
            except Exception as e:  # noqa: BLE001
                self._q.put(("scan_error", str(e)))
            finally:
                self._scanning = False

        threading.Thread(target=work, daemon=True).start()

    def _merge_quota(self, items: list[dict]) -> list[dict]:
        """额度拉取失败时保留上一次的成功数据，别让卡片突然变成一片红。

        失败的那张卡标成 stale（数据过期），右上角提示一行小字。
        """
        out = []
        for q in items or []:
            prov = q.get("provider") or ""
            if not q.get("ok") and not q.get("windows"):
                old = self._quota_cache.get(prov)
                if old and old.get("windows"):
                    merged = dict(old)
                    merged["stale"] = True
                    merged["error"] = q.get("error") or ""
                    out.append(merged)
                    continue
            else:
                self._quota_cache[prov] = dict(q)
            out.append(q)
        return out

    def _start_quota(self):
        """后台线程拉订阅额度（网络请求，不能阻塞 UI）。"""
        def work():
            try:
                from ..quota import fetch_all
                self._q.put(("quota_done", fetch_all()))
            except Exception:  # noqa: BLE001
                self._q.put(("quota_done", []))
        threading.Thread(target=work, daemon=True).start()

    # ---- 云同步 ----------------------------------------------------------
    def reload_sync(self) -> None:
        """重新读同步配置（设置窗口保存/同步完成后回调）。"""
        try:
            self._sync_cfg = syncmod.load_config()
        except Exception:  # noqa: BLE001
            self._sync_cfg = None
        self._refresh_sync_note()
        self.invalidate()

    def _refresh_sync_note(self) -> None:
        """把「云同步 11:20 / 云同步失败」算成末尾的一小段状态文字。"""
        cfg = self._sync_cfg
        if cfg is None or not cfg.ready():
            self._sync_note = ""
            self._sync_failed = False
            return
        self._sync_failed = cfg.last_status == "error"
        if self._sync_failed:
            self._sync_note = "云同步失败"
        elif cfg.last_sync_at:
            self._sync_note = "云同步 " + time.strftime(
                "%H:%M", time.localtime(cfg.last_sync_at / 1000))
        else:
            self._sync_note = "云同步待首次"

    def sync_now(self, force: bool = True) -> bool:
        """立刻同步一次（后台线程）。返回 False 表示没配置或正在同步。"""
        if self._syncing:
            return False
        cfg = self._sync_cfg or syncmod.load_config()
        self._sync_cfg = cfg
        if not cfg.ready():
            return False
        self._syncing = True

        def work():
            try:
                res = syncmod.sync_once(self.store, cfg, force=force)
            except Exception as e:  # noqa: BLE001
                res = syncmod.SyncResult(ok=False, error=f"{type(e).__name__}: {e}")
            finally:
                self._syncing = False
            try:
                self._q.put(("sync_done", res))
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()
        return True

    def request_sync_window(self) -> None:
        """请求打开同步设置窗。

        IPC 回调跑在后台线程，而建窗口必须回到 UI 线程（窗口的消息循环
        属于创建它的线程，错线程建出来的窗口收不到任何消息）。
        这里只置一个布尔，真正的创建交给 500ms 的刷新定时器。
        """
        self._pending_sync_win = True

    def _maybe_sync(self) -> None:
        """定时器每分钟问一次：到点且没在跑就同步。"""
        cfg = self._sync_cfg
        if cfg is None:
            try:
                self._sync_cfg = cfg = syncmod.load_config()
            except Exception:  # noqa: BLE001
                return
        if self._syncing or not cfg.ready():
            return
        if not syncmod.is_due(cfg):
            return
        self.sync_now(force=False)

    # ==================================================================
    # 绘制
    # ==================================================================
    def draw(self, c: Canvas):
        c.fill(BASE)
        try:
            self._load()
        except Exception as e:  # noqa: BLE001
            # 扫描线程写库时偶尔会 database is locked，
            # 不能因此把整帧画崩 —— 保留上一次的数据继续画。
            self._status_error = f"数据读取失败: {e}"
        self._draw_titlebar(c)
        self._draw_search(c)
        self._draw_header(c)
        if self._view_idx == 3:
            self._draw_quota(c)
        else:
            self._draw_kpis(c)
            self._draw_table(c)
        self._draw_footer(c)
        self._draw_ctx_menu(c)

    # ---- 自绘标题栏 --------------------------------------------------
    def _tb_button_at(self, x: float, y: float) -> str:
        """返回指针下的标题栏按钮：'min' / 'close' / ''（没有）。"""
        if not (0 <= y < TB_BTN_H):
            return ""
        # 四个角让给缩放热区：右上角正好压着关闭键，不让出来的话
        # 那个角永远拖不动，而且光标会显示成关闭键的手型、实际却在缩放。
        b = self.resize_border
        w, h = self.width, self.height
        if (x <= b or x >= w - b) and (y <= b or y >= h - b):
            return ""
        if TB_MIN_X <= x < TB_MIN_X + TB_BTN_W:
            return "min"
        if TB_CLOSE_X <= x < TB_CLOSE_X + TB_BTN_W:
            return "close"
        return ""

    # ---- 搜索框 ----------------------------------------------------------
    def _search_rect(self) -> tuple[float, float, float, float]:
        """搜索框在标题栏右侧、最小化按钮左边。"""
        w = 170.0
        h = 20.0
        x = TB_MIN_X - w - 12
        y = (TITLE_H - h) / 2
        return (x, y, w, h)

    def _search_box_at(self, x: float, y: float) -> bool:
        sx, sy, sw, sh = self._search_rect()
        return sx <= x <= sx + sw and sy <= y <= sy + sh

    def _draw_search(self, c: Canvas):
        x, y, w, h = self._search_rect()
        focused = self._search_focus
        c.round_rect(x, y, w, h, h / 2,
                     fill=SURFACE_2 if focused else SURFACE,
                     stroke=ACCENT if focused else LINE_2,
                     stroke_w=1.0)
        # 放大镜图标（圆环 + 手柄）
        cx, cy = x + 12, y + h / 2
        c.round_rect(cx - 4, cy - 4.5, 8, 8, 4, fill=None,
                     stroke=TEXT_3, stroke_w=1.3)
        c.line(cx + 2.8, cy + 3.2, cx + 6, cy + 6.4, TEXT_3, 1.3)
        # 文本 / 占位
        txt = self._search_q if self._search_q else "搜索工具 / 模型…"
        col = TEXT if self._search_q else TEXT_3
        c.text(x + 22, y, w - 30, h, txt, self.f_small, col,
               align=DT_L | DT_VC | DT_SL)
        # 清除按钮
        if self._search_q:
            c.line(x + w - 14, y + h / 2 - 4, x + w - 6, y + h / 2 + 4, TEXT_3, 1.2)
            c.line(x + w - 14, y + h / 2 + 4, x + w - 6, y + h / 2 - 4, TEXT_3, 1.2)

    def _row_matches(self, row: dict) -> bool:
        """搜索过滤：name / sub / key 任一包含关键字（不区分大小写）即命中。"""
        if not self._search_q:
            return True
        q = self._search_q.lower()
        for f in ("name", "sub", "key"):
            v = row.get(f) or ""
            if q in str(v).lower():
                return True
        return False

    # ---- 右键菜单 --------------------------------------------------------
    def _ctx_hit_item(self, x: float, y: float) -> int:
        if not self._ctx_items:
            return -1
        item_h = 26.0
        pad = 6.0
        menu_w = 180.0
        mx, my = self._ctx_x, self._ctx_y
        # 越界翻转
        if mx + menu_w > self.width:
            mx = self.width - menu_w - 4
        if my + pad + item_h * len(self._ctx_items) + pad > self.height:
            my = self.height - (pad + item_h * len(self._ctx_items) + pad) - 4
        for i in range(len(self._ctx_items)):
            iy = my + pad + i * item_h
            if mx <= x <= mx + menu_w and iy <= y <= iy + item_h:
                return i
        return -1

    def _draw_ctx_menu(self, c: Canvas):
        if not self._ctx_items:
            return
        item_h = 26.0
        pad = 6.0
        menu_w = 180.0
        menu_h = pad * 2 + item_h * len(self._ctx_items)
        mx, my = self._ctx_x, self._ctx_y
        if mx + menu_w > self.width:
            mx = self.width - menu_w - 4
        if my + menu_h > self.height:
            my = self.height - menu_h - 4
        # 投影 + 面 + 描边
        c.round_rect(mx, my + 1.5, menu_w, menu_h, 8, fill=SHADOW)
        c.round_rect(mx, my, menu_w, menu_h, 8, fill=SURFACE_2,
                     stroke=LINE_2, stroke_w=1.0)
        for i, (mid, label) in enumerate(self._ctx_items):
            iy = my + pad + i * item_h
            if i == self._ctx_hot:
                c.round_rect(mx + 4, iy, menu_w - 8, item_h, 6, fill=SURFACE_3)
            col = DANGER if mid == "hide" else TEXT
            c.text(mx + 12, iy, menu_w - 24, item_h, label,
                   self.f_small, col, align=DT_L | DT_VC | DT_SL)

    def _open_ctx_menu(self, x: float, y: float, row: dict):
        self._ctx_row = self._row_at(x, y)
        self._ctx_x = x
        self._ctx_y = y
        self._ctx_hot = -1
        items = []
        key = row.get("key", "")
        if row.get("kind") in ("app", "model", "srow"):
            if row.get("open"):
                items.append(("collapse", "收起明细"))
            else:
                items.append(("expand", "展开明细"))
            items.append(("filter", f"只看「{row.get('name', '')}」"))
            items.append(("copy", "复制名称"))
            items.append(("copy_tok", "复制 Token 数"))
        self._ctx_items = items
        self.invalidate()

    def _exec_ctx(self, idx: int):
        if idx < 0 or idx >= len(self._ctx_items):
            self._ctx_items = []
            return
        mid, label = self._ctx_items[idx]
        rows = self._rows
        row = rows[self._ctx_row] if 0 <= self._ctx_row < len(rows) else None
        if mid == "sep":
            self._ctx_items = []
            self.invalidate()
            return
        if mid == "expand" and row is not None:
            self._expanded.add(row["key"])
        elif mid == "collapse" and row is not None:
            self._expanded.discard(row["key"])
        elif mid == "filter" and row is not None:
            self._search_q = row.get("name", "")
            self._search_focus = True
        elif mid == "copy" and row is not None:
            self._clipboard(row.get("name", ""))
        elif mid == "copy_tok" and row is not None:
            cells = row.get("cells") or []
            if cells:
                self._clipboard(cells[0][0])
        self._ctx_items = []
        self._ctx_row = -1
        self.invalidate()

    @staticmethod
    def _clipboard(text: str):
        """Win32 剪贴板。失败静默——这功能不能影响主流程。"""
        try:
            import ctypes
            from ctypes import wintypes
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            if not u32.OpenClipboard(0):
                return
            try:
                u32.EmptyClipboard()
                data = (text + "\0").encode("utf-16-le")
                h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not h:
                    return
                p = k32.GlobalLock(h)
                ctypes.memmove(p, data, len(data))
                k32.GlobalUnlock(h)
                u32.SetClipboardData(CF_UNICODETEXT, h)
            finally:
                u32.CloseClipboard()
        except Exception:
            pass

    # ---- 通用卡片 ------------------------------------------------------
    @staticmethod
    def _card(c: Canvas, x, y, w, h, r=14, fill=SURFACE, border=CARD_LINE,
              highlight=True):
        """一块卡片的完整材质：投影 + 面 + 描边 + 顶边高光。"""
        c.round_rect(x, y + 1.5, w, h, r, fill=SHADOW)
        c.round_rect(x, y, w, h, r, fill=fill, stroke=border, stroke_w=1.0)
        if highlight:
            c.line(x + r, y + 1, x + w - r, y + 1, CARD_TOP, 1)

    def _draw_titlebar(self, c: Canvas):
        # 左侧：一个圆角小图标（三根递增柱 = 消耗曲线）+ 名称 + 副标题
        ix, iy, isz = 12, (TITLE_H - 20) / 2, 20
        c.round_rect(ix, iy, isz, isz, 6, fill=mix(SURFACE_2, ACCENT, 0.16),
                     stroke=mix(SURFACE_2, ACCENT, 0.32), stroke_w=1.0)
        for i, (bh, col) in enumerate([(4, "#6C7A96"), (7, "#A9B8D2"),
                                       (10, ACCENT)]):
            c.round_rect(ix + 5 + i * 4, iy + 10 - bh, 3, bh, 1.5, fill=col)
        c.text(ix + isz + 8, 0, 160, TITLE_H, "TokenBoard", self.f_title_s,
               TEXT, align=DT_L | DT_VC | DT_SL)
        # 竖分隔 + 副标题
        c.line(ix + isz + 8 + 76, TITLE_H / 2 - 5,
               ix + isz + 8 + 76, TITLE_H / 2 + 5, LINE_2, 1)
        c.text(ix + isz + 8 + 88, 0, 280, TITLE_H, "本机 AI 编程用量 · 成本 · 速度",
               self.f_tiny, TEXT_3, align=DT_L | DT_VC | DT_SL)

        cy = TITLE_H / 2
        for key, x0 in (("min", TB_MIN_X), ("close", TB_CLOSE_X)):
            hot = self._hover_tb == key
            if hot:
                c.fill_rect(x0, 0, TB_BTN_W, TB_BTN_H,
                            "#E5484D" if key == "close" else SURFACE_3)
            gcol = "#FFFFFF" if (hot and key == "close") else TEXT_2
            cx = x0 + TB_BTN_W / 2
            if key == "min":
                c.line(cx - 5, cy, cx + 5, cy, gcol, 1)
            else:
                c.line(cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5, gcol, 1)
                c.line(cx + 4.5, cy - 4.5, cx - 4.5, cy + 4.5, gcol, 1)

        c.line(0, TITLE_H - 1, WIN_W, TITLE_H - 1, LINE)

    # ---- 顶部控件条 --------------------------------------------------
    def _draw_header(self, c: Canvas):
        self._draw_seg(c, PAD, SEG_Y, VIEW_SEG_W,
                       [v[0] for v in VIEWS], self._view_idx)
        if self._view_idx == 3:
            # 额度是实时的，时间范围对它没意义 —— 换成刷新说明
            c.text(WIN_W - PAD - 240, SEG_Y + 4, 240, 16,
                   "额度每 5 分钟自动刷新", self.f_small, TEXT_3,
                   align=DT_R | DT_VC | DT_SL)
        else:
            self._draw_seg(c, PERIOD_SEG_X, SEG_Y, PERIOD_SEG_W,
                           [p[0] for p in PERIODS], self._period_idx)
        c.line(0, TITLE_H + HEAD_H, WIN_W, TITLE_H + HEAD_H, LINE)

    def _draw_seg(self, c: Canvas, x, y, w, items, sel):
        n = len(items)
        # 药丸容器：面 + 1px 描边，选中项再压一层亮面和顶边高光
        c.round_rect(x - 3, y - 3, w * n + 6, SEG_H + 6, (SEG_H + 6) / 2,
                     fill=SURFACE_2, stroke=CARD_LINE, stroke_w=1.0)
        for i, name in enumerate(items):
            ix = x + i * w
            if i == sel:
                c.round_rect(ix, y, w, SEG_H, SEG_H / 2,
                             fill=mix(SURFACE_3, ACCENT, 0.22),
                             stroke=mix(SURFACE_3, ACCENT, 0.5),
                             stroke_w=1.0)
                c.line(ix + 10, y + 1, ix + w - 10, y + 1,
                       mix(mix(SURFACE_3, ACCENT, 0.22), "#FFFFFF", 0.16), 1)
                c.text(ix, y, w, SEG_H, name, self.f_seg_sel, TEXT,
                       align=DT_C | DT_VC | DT_SL)
            else:
                c.text(ix, y, w, SEG_H, name, self.f_seg, TEXT_2,
                       align=DT_C | DT_VC | DT_SL)

    # ---- 顶部指标卡 --------------------------------------------------
    def _draw_kpis(self, c: Canvas):
        t = self._totals
        sp = (self._speed or {}).get("total") or {}
        total = t.get("total") or 0
        cost = t.get("cost") or 0.0
        ttft_n = sp.get("n_ttft") or 0
        tps = sp.get("tps") or 0
        n_call = sp.get("n_call") or 0

        per_m = (cost / total * 1e6) if total else 0.0
        tiles = [
            {
                "label": "总消耗",
                "value": fmt_tokens(total),
                "sub1": f"{PERIODS[self._period_idx][0]} · "
                        f"{t.get('reqs', 0):,} 次请求",
                "sub2": f"入 {fmt_tokens(t.get('input'))} · "
                        f"出 {fmt_tokens(t.get('output'))} · "
                        f"缓存 {fmt_tokens(t.get('cache'))}",
                "spark": True,
                "tone": ACCENT,
            },
            {
                "label": "成本",
                "value": fmt_money(cost),
                "sub1": f"≈ {fmt_cny(cost)}",
                "sub2": f"{fmt_money(per_m)} / M tokens" if total else "无价格数据",
                "tone": COST,
            },
            {
                "label": "首字（TTFT）",
                "value": fmt_ms(sp.get("ttft_p50")),
                "sub1": (f"P90 {fmt_ms(sp.get('ttft_p90'))}" if ttft_n
                         else "本期无采样"),
                "sub2": (f"{ttft_n:,} 次采样" if ttft_n
                         else "Codex / OpenCode 提供"),
                "tone": LATENCY,
            },
            {
                "label": "输出速度",
                "value": f"{tps:.0f}" if tps else "—",
                "unit": "tok/s" if tps else "",
                "sub1": (f"输出 {fmt_tokens(sp.get('out'))}" if tps
                         else "本期无采样"),
                "sub2": (f"{n_call:,} 次调用 · 均 {fmt_ms(sp.get('dur_avg'))}"
                         if tps else "OpenCode / DSH / ZCode 提供"),
                "tone": SPEED,
            },
        ]

        for i, tile in enumerate(tiles):
            self._draw_kpi_tile(c, KPI_X[i], KPI_Y, KPI_W[i], KPI_H, tile)

    def _draw_kpi_tile(self, c: Canvas, x, y, w, h, tile: dict):
        # 卡面统一带一点底色（别让四张卡变成红绿灯），
        # 指标的「身份色」只在左侧竖条和描边上出现：蓝=用量、绿=成本、琥珀=首字、紫=速度。
        tone = tile.get("tone") or ACCENT
        primary = bool(tile.get("spark"))
        fill = mix(SURFACE, ACCENT, 0.045 if primary else 0.03)
        self._card(c, x, y, w, h, 14, fill=fill,
                   border=mix(CARD_LINE, tone, 0.42))
        pad = 14
        spark = primary
        text_w = w - pad * 2 - (86 if spark else 0)

        # 标签左边一小段强调色竖条，标出这块指标的身份色
        c.round_rect(x + pad, y + 12, 3, 12, 1.5, fill=tone)
        c.text(x + pad + 10, y + 11, w - pad * 2 - 10, 14, tile["label"],
               self.f_kpi_label, TEXT_2, align=DT_L | DT_VC | DT_SL)

        # 大数字：窄窗口下自动降一档字号，别让「104 tok/s」被裁掉
        value = tile["value"]
        font = self.f_kpi
        vw, _ = c.measure(value, font)
        unit = tile.get("unit") or ""
        uw = 0
        if unit:
            uw, _ = c.measure(" " + unit, self.f_kpi_unit)
        if vw + uw > text_w and self.f_kpi_m:
            font = self.f_kpi_m
        c.text(x + pad, y + 26, text_w, 32, value, font, TEXT,
               align=DT_L | DT_VC | DT_SL)
        if unit:
            c.text(x + pad + min(vw, text_w) + 4, y + 38, 60, 16, unit,
                   self.f_kpi_unit, TEXT_3, align=DT_L | DT_VC | DT_SL)

        c.text(x + pad, y + 61, text_w, 13, tile["sub1"], self.f_kpi_sub,
               TEXT_2, align=DT_L | DT_VC | DT_SL)
        c.text(x + pad, y + 75, text_w, 13, tile["sub2"], self.f_kpi_sub,
               TEXT_3, align=DT_L | DT_VC | DT_SL)

        if spark:
            sx = x + w - 86
            self._draw_spark(c, sx, y + 28, 74, 46)

    def _draw_spark(self, c: Canvas, x, y, w, h):
        vals = self._spark
        if not vals or max(vals) <= 0:
            c.text(x, y + h / 2 - 8, w, 16, "暂无数据", self.f_tiny, TEXT_3,
                   align=DT_C | DT_VC | DT_SL)
            return
        n = len(vals)
        mx = max(vals)
        base = y + h
        pts = []
        for i, v in enumerate(vals):
            px = x + w * i / (n - 1)
            py = base - (h - 4) * (v / mx)
            pts.append((px, py))

        # 面积：横向分带逼近垂直渐变（深色界面里没有 alpha 通道）
        top = min(p[1] for p in pts)
        span = max(1.0, base - top)
        for row in range(int(span) + 1):
            yb = base - row
            xs = [p[0] for p in pts if p[1] <= yb]
            if not xs:
                break
            tt = row / span
            c.fill_rect(min(xs), yb, max(1.0, max(xs) - min(xs)), 1,
                        mix(SURFACE, ACCENT, 0.34 * (1 - tt) ** 1.5))
        c.polyline(pts, ACCENT, 1.6)
        c.ellipse(pts[-1][0] - 2.5, pts[-1][1] - 2.5, 5, 5, ACCENT)

    # ---- 明细表 ------------------------------------------------------
    def _row_height(self, row: dict) -> int:
        return ROW_SUB if row["kind"] in ("sub", "ssub") else ROW_MAIN

    def _layout_rows(self) -> None:
        """算好每行的 y 坐标（不依赖是否已经画过）。"""
        self._row_y = []
        y = BODY_Y
        for r in self._rows:
            self._row_y.append(y)
            y += self._row_height(r)
        self._content_h = y - BODY_Y

    def _visible_count(self) -> int:
        used = 0
        n = 0
        for r in self._rows:
            h = self._row_height(r)
            if used + h > BODY_H:
                break
            used += h
            n += 1
        return max(1, n)

    def _max_scroll(self) -> int:
        return max(0, len(self._rows) - self._visible_count())

    def _scroll_base(self) -> float:
        if not self._row_y:
            return BODY_Y
        return self._row_y[min(self._scroll, len(self._row_y) - 1)]

    def _row_rect(self, i: int) -> tuple[float, float, float, float]:
        """第 i 行在当前滚动位置下的屏幕矩形 (x, y, w, h)。"""
        y = BODY_Y + (self._row_y[i] - self._scroll_base())
        return (PAD - 6, y, WIN_W - PAD * 2 + 12, self._row_height(self._rows[i]))

    def _row_at(self, x: float, y: float) -> int:
        for i, row in enumerate(self._rows):
            if row["kind"] in ("sub", "ssub"):
                continue
            rx, ry, rw, rh = self._row_rect(i)
            if ry <= y < ry + rh and rx <= x < rx + rw:
                return i
        return -1

    def _draw_table(self, c: Canvas):
        rows = self._rows
        if not rows:
            if self._search_q:
                hint = f"没有匹配「{self._search_q}」的行"
            elif self._view_idx != 2:
                hint = "本期没有用量"
            else:
                hint = "本期还没有速度采样"
            c.text(PAD, BODY_Y + 22, WIN_W - PAD * 2, 20, hint, self.f_small,
                   TEXT_3, align=DT_L | DT_VC | DT_SL)
            if self._view_idx == 2:
                c.text(PAD, BODY_Y + 44, WIN_W - PAD * 2, 20,
                       "首字来自 Codex / OpenCode，吞吐来自 OpenCode / DSH / ZCode",
                       self.f_tiny, TEXT_3, align=DT_L | DT_VC | DT_SL)
            return

        self._scroll = max(0, min(self._scroll, self._max_scroll()))
        base = self._scroll_base()
        footer_h = 26                     # 卡片底部的「合计」行
        bottom = BODY_Y + BODY_H - footer_h

        # 先算这一屏画得下几行：列表卡片按内容高度收紧，
        # 这样行数少的时候卡片不会被拉成一整块空面板
        drawn = 0
        used = 0.0
        for i in range(self._scroll, len(rows)):
            y = BODY_Y + (self._row_y[i] - base)
            h = self._row_height(rows[i])
            if y + h > bottom:
                break
            drawn += 1
            used += h

        card_top = COL_HEAD_Y - 8
        body_bottom = BODY_Y + BODY_H
        # 卡片永远贴着内容收（行数多时正好铺满内容区）：
        # 收得比内容区短，下面那点空隙是「留白」；拉满反而会露出半张空卡片。
        card_h = (BODY_Y + used + 8) - card_top + footer_h
        strip_top = card_top + card_h + 10
        strip_h = min(150.0, body_bottom - strip_top)
        with_chart = strip_h >= 72 and len(self._spark) >= 2
        if with_chart:
            # 有图表时把卡片底部那点留白收紧，给图表腾高度
            strip_h = min(strip_h, body_bottom - strip_top)

        self._card(c, PAD - 8, card_top, WIN_W - PAD * 2 + 16, card_h, 14)

        # 表头（压在卡片顶部内侧，和数据行一起构成一张表）
        cols = VIEW_COLS.get(self._view_idx, VIEW_COLS[0])
        left_head = "工具" if self._view_idx == 0 else "模型"
        c.text(NAME_X, COL_HEAD_Y, 200, COL_HEAD_H, left_head, self.f_head,
               TEXT_3, align=DT_L | DT_VC | DT_SL)
        for i, label in enumerate(cols):
            c.text(COL_X[i], COL_HEAD_Y, COL_W[i], COL_HEAD_H, label,
                   self.f_head, TEXT_3, align=DT_R | DT_VC | DT_SL)
        c.line(PAD, COL_HEAD_Y + COL_HEAD_H + 2, WIN_W - PAD,
               COL_HEAD_Y + COL_HEAD_H + 2, LINE, 1)

        token = c.push_clip(PAD - 10, BODY_Y - 2, WIN_W - PAD * 2 + 20,
                            card_h - footer_h - 22)
        for i in range(self._scroll, self._scroll + drawn):
            y = BODY_Y + (self._row_y[i] - base)
            self._draw_row(c, rows[i], y, self._row_height(rows[i]), i,
                           last=(i == self._scroll + drawn - 1))
        c.pop_clip(token)

        self._draw_totals(c, card_top + card_h - footer_h)

        if with_chart:
            self._draw_daily_strip(c, strip_top, strip_h)

        if len(rows) > drawn:
            track_h = card_h - footer_h - 30
            frac = max(0.12, drawn / len(rows))
            thumb_h = max(20, int(track_h * frac))
            pos = int((track_h - thumb_h) *
                      (self._scroll / max(1, len(rows) - drawn)))
            c.round_rect(SCROLL_X, BODY_Y, 3, track_h, 2, fill=SURFACE_2)
            c.round_rect(SCROLL_X, BODY_Y + pos, 3, thumb_h, 2, fill=LINE_2)

    # ---- 卡片底部合计行 ------------------------------------------------
    def _draw_totals(self, c: Canvas, y: float):
        """合计行：把这一屏的数字收个尾，也顺手填掉卡片底部的空白。"""
        c.line(PAD, y, WIN_W - PAD, y, LINE, 1)
        t = self._totals
        sp = (self._speed or {}).get("total") or {}
        # 标签带上「多少个工具/模型」，滚到一半时也能知道这一屏以外还有东西
        # （只数主行，展开出来的模型子行不算）
        unit = "个工具" if self._view_idx == 0 else "个模型"
        n_main = sum(1 for r in self._rows if r["kind"] in ("app", "model", "srow"))
        c.text(NAME_X, y + 5, 200, 16, f"合计 · {n_main} {unit}",
               self.f_meta, TEXT_3, align=DT_L | DT_VC | DT_SL)

        if self._view_idx == 2:      # 速度视图：首字 / tok/s / 输出 / 样本
            cells = [
                (fmt_ms(sp.get("ttft_p50")), bool(sp.get("n_ttft"))),
                (fmt_tps(sp.get("tps")), bool(sp.get("tps"))),
                (fmt_tokens(sp.get("out")) if sp.get("out") else "—",
                 bool(sp.get("out"))),
                (f"{sp.get('n') or 0:,}", bool(sp.get("n"))),
            ]
        else:
            cells = [
                (fmt_tokens(t.get("total")), True),
                (fmt_money(t.get("cost")), True),
                (fmt_ms(sp.get("ttft_p50")), bool(sp.get("n_ttft"))),
                (fmt_tps(sp.get("tps")), bool(sp.get("tps"))),
            ]
        for i, (text, has) in enumerate(cells):
            c.text(COL_X[i], y + 5, COL_W[i], 16, text, self.f_numb,
                   TEXT_2 if has else TEXT_3, align=DT_R | DT_VC | DT_SL)

    # ---- 近 N 天柱状图（列表没占满时补在下面）--------------------------
    def _strip_days(self) -> int:
        """柱子根数跟着时间范围走：7 天就看 7 根。"""
        days = PERIODS[self._period_idx][1]
        if days == 7:
            return 7
        if days in (30, None):
            return 30
        return 14          # 「今天」也给两周做对比

    def _draw_daily_strip(self, c: Canvas, top: float, h: float):
        n_days = self._strip_days()
        vals = self._spark[-n_days:]
        if len(vals) < 2 or max(vals) <= 0:
            return

        # 整块做成一张卡片，比一排悬空的柱子和上面的表格更成体系
        self._card(c, PAD, top, WIN_W - PAD * 2, h, 14)
        inset = PAD + 16
        w = WIN_W - PAD * 2 - 32
        n = len(vals)
        mx = max(vals)

        # 空间紧的时候分两档退化：
        #   compact   —— 不写日期，只留柱子和数值；
        #   tiny      —— 连数值也不写，只剩柱子和标题（再挤就快看不出高低了）。
        compact = h < 118
        tiny = h < 86
        head_h = 20 if tiny else (26 if compact else 30)
        label_h = 0 if (compact or n > 14) else 14
        slot = w / n
        show_val = (not tiny) and slot >= 30
        val_h = 12 if show_val else 0

        c.text(inset, top + (4 if compact else 10), 240, 14,
               f"近 {n} 天每日消耗", self.f_meta, TEXT_3,
               align=DT_L | DT_VC | DT_SL)
        # 柱子上有数值时就不用再单独写峰值，避免同一个数出现两次
        if not show_val:
            c.text(WIN_W - PAD - 16 - 180, top + (4 if compact else 10), 180, 14,
                   f"峰值 {fmt_tokens(mx)}", self.f_tinyb, TEXT_3,
                   align=DT_R | DT_VC | DT_SL)

        by = top + head_h + val_h          # 数值标签也占一行，所以柱子整体再往下让 12px
        bh = max(16.0, h - head_h - 8 - label_h - val_h)
        base = by + bh

        # 柱子占满整宽：柱宽取格子的 70%（封顶 56），剩下的是间距 ——
        # 天数少的时候不会中间挤成一小撮、两边留一大片空
        bw = min(56.0, max(10.0, slot * 0.70))
        gap = max(3.0, slot - bw)
        x0 = inset + (w - (n * bw + gap * (n - 1))) / 2

        # 三条网格线：给高度一个参照，柱子不再是浮在空中的色块
        for frac in (0.25, 0.5, 0.75):
            gy = base - bh * frac
            c.line(inset, gy, inset + w, gy, GRID, 1)
        c.line(inset, base + 1, inset + w, base + 1, LINE, 1)

        today = datetime.now()
        for i, v in enumerate(vals):
            bx = x0 + i * (bw + gap)
            hh = max(3.0, bh * v / mx) if v > 0 else 1.5
            is_today = i == n - 1
            # 日常柱用偏亮的蓝（太暗会跟蓝板岩底子糊在一起），今天用主强调色
            col = ACCENT if is_today else mix(SURFACE_3, ACCENT, 0.55)
            c.round_rect(bx, base - hh, bw, hh, 3, fill=col)
            if is_today and hh > 8:
                # 今天的柱子顶上点一颗亮点，视线一下就找到「现在」
                c.ellipse(bx + bw / 2 - 2, base - hh - 5, 4, 4, ACCENT)
            if show_val:
                c.text(bx - 14, base - hh - val_h - 1, bw + 28, 12,
                       fmt_tokens(v) if v else "", self.f_tiny,
                       TEXT_2 if is_today else TEXT_3,
                       align=DT_C | DT_VC | DT_SL)

            if label_h and (n <= 8 or i % 2 == 0 or is_today):
                d = (today - timedelta(days=n - 1 - i)).strftime("%m-%d")
                c.text(bx - 8, base + 4, bw + 16, 12,
                       "今天" if is_today else d, self.f_tiny,
                       TEXT_2 if is_today else TEXT_3,
                       align=DT_C | DT_VC | DT_SL)

    def _draw_row(self, c: Canvas, row: dict, y: float, h: float, idx: int = -1,
                  last: bool = False):
        kind = row["kind"]
        main = kind in ("app", "model", "srow")
        color = row["color"]

        if main and idx == self._hover_row:
            # 悬停：整行压一层浅底 + 左侧强调条，鼠标在哪一行一眼看得出
            c.round_rect(PAD - 4, y + 1, WIN_W - PAD * 2 + 8, h - 2, 10,
                         fill=ROW_HOVER)
            c.round_rect(PAD - 4, y + 1, 2, h - 2, 1,
                         fill=mix(ROW_HOVER, color, 0.9))

        if main:
            # 品牌色竖条 + 展开箭头 + 名称（第二行小字）
            c.round_rect(PAD, y + 9, TICK_W, h - 18, 1.5,
                         fill=color if not (idx == self._hover_row)
                         else mix(color, "#FFFFFF", 0.22))
            c.text(PAD + 9, y + 7, 12, 16,
                   DISCLOSURE_OPEN if row.get("open") else DISCLOSURE_CLOSED,
                   self.f_tiny, TEXT_2, align=DT_L | DT_VC | DT_SL)
            c.text(NAME_X, y + 5, NAME_W, 18, row["name"], self.f_name, TEXT,
                   align=DT_L | DT_VC | DT_SL)
            if row.get("sub"):
                c.text(NAME_X, y + 24, BAR_END - NAME_X - 6, 14, row["sub"],
                       self.f_name_sub, TEXT_3, align=DT_L | DT_VC | DT_SL)
            # 进度条与数值行居中对齐：轨道按品牌色染一点，条 + 末端高光
            c.round_rect(BAR_X, y + 14, BAR_W, 5, 2.5,
                         fill=mix(SURFACE, color, 0.18))
            bw = max(2.0, BAR_W * max(0.0, min(1.0, row.get("bar") or 0)))
            c.round_rect(BAR_X, y + 14, bw, 5, 2.5, fill=color)
            if bw > 4:
                c.fill_rect(BAR_X + bw - 2, y + 14.5, 1.5, 4,
                            mix(color, "#FFFFFF", 0.55))
            cy, chh = y + 8, 18
            font = self.f_cell
            # 行底一条极淡的分隔线，扫读时不至于串行（最后一行贴着卡片边，不画）
            if not last:
                c.line(NAME_X, y + h - 1, WIN_W - PAD - 2, y + h - 1, LINE, 1)
        else:
            # 子行：一条竖引导线 + 端点圆点，代替纯缩进
            c.line(PAD + 13.5, y, PAD + 13.5, y + h, LINE, 1)
            c.ellipse(PAD + 11, y + 9, 6, 6, mix(SURFACE, color, 0.22))
            c.ellipse(PAD + 12, y + 10, 4, 4, color)
            c.text(PAD + 26, y + 5, NAME_W + 10, 16, row["name"],
                   self.f_small, TEXT_2, align=DT_L | DT_VC | DT_SL)
            c.round_rect(BAR_X, y + 11, BAR_W, 4, 2,
                         fill=mix(SURFACE, color, 0.18))
            bw = max(1.0, BAR_W * max(0.0, min(1.0, row.get("bar") or 0)))
            c.round_rect(BAR_X, y + 11, bw, 4, 2, fill=color)
            cy, chh = y + 5, 16
            font = self.f_cell_s

        for i, (text, col) in enumerate(row["cells"]):
            c.text(COL_X[i], cy, COL_W[i], chh, text, font, col,
                   align=DT_R | DT_VC | DT_SL)

    # ---- 订阅额度 ----------------------------------------------------
    def _quota_blocks(self) -> list[tuple[dict, float]]:
        """返回 [(额度项, 卡片高度)]，高度随限额条数和提示行数变化。"""
        out = []
        for q in (self._quota or []):
            wins = q.get("windows") or []
            if wins:
                h = 26 + len(wins) * 40 + 12
            else:
                h = 72 if q.get("hint") else 58
            out.append((q, h))
        return out

    def _draw_quota(self, c: Canvas):
        blocks = self._quota_blocks()
        if not blocks:
            self._card(c, PAD, QUOTA_Y, QUOTA_W, 64, 14)
            c.text(PAD + 18, QUOTA_Y + 22, QUOTA_W - 36, 20, "正在获取订阅额度…",
                   self.f_meta, TEXT_3, align=DT_L | DT_VC | DT_SL)
            return

        gap = QUOTA_GAP
        total = sum(h for _, h in blocks) + gap * (len(blocks) - 1)
        max_scroll = max(0.0, total - QUOTA_H)
        self._quota_scroll = max(0.0, min(self._quota_scroll, max_scroll))

        token = c.push_clip(PAD, QUOTA_Y, QUOTA_W, QUOTA_H)
        y = QUOTA_Y - self._quota_scroll
        for q, h in blocks:
            self._draw_quota_card(c, q, y, h, QUOTA_W)
            y += h + gap
        c.pop_clip(token)

        if total > QUOTA_H:
            frac = max(0.12, QUOTA_H / total)
            thumb_h = max(20, int(QUOTA_H * frac))
            pos = int((QUOTA_H - thumb_h) * (self._quota_scroll /
                                             max(1.0, total - QUOTA_H)))
            c.round_rect(SCROLL_X, QUOTA_Y, 3, QUOTA_H, 2, fill=SURFACE_2)
            c.round_rect(SCROLL_X, QUOTA_Y + pos, 3, thumb_h, 2, fill=LINE_2)

    def _draw_quota_card(self, c: Canvas, q: dict, y: float, h: float,
                         w: float):
        self._card(c, PAD, y, w, h, 14)
        color = QUOTA_COLOR.get(q.get("provider", ""), ACCENT)

        ok = q.get("ok")
        stale = bool(q.get("stale"))
        dot = WARN if stale else ("#FFFFFF" if ok else
                                 (DANGER if q.get("error") else LINE_2))
        c.ellipse(PAD + 16, y + 13, 7, 7, dot)
        c.text(PAD + 30, y + 8, 300, 18, q.get("name", ""), self.f_name, TEXT,
               align=DT_L | DT_VC | DT_SL)

        right = q.get("note") or ""
        if not right and q.get("windows"):
            right = f"{len(q['windows'])} 项限额"
        if right:
            c.text(PAD + w - 260, y + 9, 244, 16, right, self.f_small, TEXT_3,
                   align=DT_R | DT_VC | DT_SL)
        if stale:
            c.text(PAD + w - 260, y + 24, 244, 14, "更新失败 · 显示上次数据",
                   self.f_tiny, WARN, align=DT_R | DT_VC | DT_SL)

        wins = q.get("windows") or []
        if not wins:
            msg = q.get("error") or "无额度信息"
            c.text(PAD + 30, y + 32, w - 60, 16, msg, self.f_small,
                   DANGER if q.get("error") else TEXT_3, align=DT_L | DT_VC | DT_SL)
            hint = q.get("hint")
            if hint:
                c.text(PAD + 30, y + 48, w - 60, 16, hint, self.f_tiny, TEXT_3,
                       align=DT_L | DT_VC | DT_SL)
            return

        wy = y + 26
        for win in wins:
            self._draw_quota_window(c, PAD + 36, wy + 20, win, color, w)
            wy += 40

    def _draw_quota_window(self, c: Canvas, cx: float, cy: float, win: dict,
                           color: str, card_w: float):
        label = WINDOW_LABEL.get(win.get("kind", ""), win.get("kind", ""))
        used = max(0.0, min(100.0, float(win.get("used", 0))))
        remaining = max(0.0, min(100.0, float(win.get("remaining", 100 - used))))

        # 环形仪表
        self._draw_gauge(c, cx, cy, 16, used, color)
        c.text(cx - 18, cy - 8, 36, 16, f"{used:.0f}", self.f_gauge, TEXT,
               align=DT_C | DT_VC | DT_SL)

        tx = cx + 28
        c.text(tx, cy - 15, 150, 15, label, self.f_meta, TEXT_2,
               align=DT_L | DT_VC | DT_SL)
        c.text(tx, cy - 1, 190, 15, f"已用 {used:.0f}% · 剩 {remaining:.0f}%",
               self.f_tiny, TEXT_3, align=DT_L | DT_VC | DT_SL)

        until = fmt_until(win.get("reset_at") or 0)
        c.text(PAD + card_w - 150, cy - 8, 134, 16, until, self.f_small, TEXT_2,
               align=DT_R | DT_VC | DT_SL)

    @staticmethod
    def _arc_pts(cx, cy, r, start_deg, sweep_deg, n=44):
        import math
        pts = []
        for i in range(n + 1):
            a = math.radians(start_deg + sweep_deg * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts

    def _draw_gauge(self, c: Canvas, cx, cy, r, used, color):
        # 外圈柔光
        c.polyline(self._arc_pts(cx, cy, r, 135, 270),
                   tint(color, SURFACE, 0.30), 8)
        # 轨道
        c.polyline(self._arc_pts(cx, cy, r, 135, 270), LINE_2, 4)
        # 已用部分
        if used > 0:
            c.polyline(self._arc_pts(cx, cy, r, 135,
                                     270 * min(100.0, used) / 100.0), color, 4)

    # ---- 底部状态条 --------------------------------------------------
    def _draw_footer(self, c: Canvas):
        c.line(PAD, FOOT_Y - 4, WIN_W - PAD, FOOT_Y - 4, LINE)
        x = PAD
        yy = FOOT_Y
        self._dot_hit = []
        for app in APP_META:
            state = self._status.get(app)
            ok = state[0] if state else None
            # 正常态用白点（界面整体白色）；只有异常才留颜色：
            # 红=采集失败，灰=还没采到
            dot = "#FFFFFF" if ok else (DANGER if ok is False else LINE_2)
            # 小圆点外面套一圈同色淡光，比分色纯圆点更精致，也更容易看清状态
            c.ellipse(x - 1, yy + 3, 9, 9, mix(BASE, dot, 0.28))
            c.ellipse(x, yy + 4, 7, 7, dot)
            label = APP_META[app].get("short", app_label(app))
            tw, _ = c.measure(label, self.f_small)
            c.text(x + 12, yy + 1, tw + 4, 16, label, self.f_small,
                   TEXT_2 if ok else (DANGER if ok is False else TEXT_3),
                   align=DT_L | DT_VC | DT_SL)
            self._dot_hit.append((app, x, yy, 12 + tw + 4))
            x += 12 + tw + 14

        # 右侧：更新时刻 + 云同步状态（云同步在前，时间贴右）
        upd_w = 220
        sync_w = 0.0
        if self._sync_note:
            sw, _ = c.measure(self._sync_note, self.f_tiny)
            sync_w = sw + 8
            c.text(WIN_W - PAD - upd_w - sync_w, yy + 1, sync_w, 16,
                   self._sync_note, self.f_tiny,
                   DANGER if self._sync_failed else TEXT_3,
                   align=DT_R | DT_VC | DT_SL)
        # 快捷键提示（小号暗字）：贴在云同步状态左侧；空间不够不画
        hint = "1-4 切视图 · 滚轮 · R 刷新"
        hw, _ = c.measure(hint, self.f_tiny)
        hint_x = WIN_W - PAD - upd_w - sync_w - 10 - hw
        if hint_x > x + 10:
            c.text(hint_x, yy + 1, hw, 16, hint, self.f_tiny, TEXT_3,
                   align=DT_L | DT_VC | DT_SL)
        # 右侧：更新时刻，前面加一个极小的状态灯（有错就变红）
        msg = self._footer_msg()
        col = DANGER if self._status_error else TEXT_3
        c.text(WIN_W - PAD - upd_w, yy + 1, upd_w, 16, msg, self.f_small, col,
               align=DT_R | DT_VC | DT_SL)

    def _footer_msg(self) -> str:
        if self._status_error:
            return self._status_error
        return f"更新于 {self._last_update}"

    def _jump_to_app(self, app: str) -> None:
        """点状态点：切到「按工具」视图，展开该工具并滚到它那一行。"""
        self._view_idx = 0
        self._expanded.add(app)
        self._load()
        for i, row in enumerate(self._rows):
            if row["kind"] == "app" and row["key"] == app:
                self._scroll = max(0, i - 1)
                break
        state = self._status.get(app)
        if state and not state[0] and state[1]:
            self._status_error = f"{app_label(app)} 采集失败：{state[1][:40]}"
        self.invalidate()

    # ------------------------------------------------------------- 交互
    def _seg_hit(self, x: float, y: float, x0: float, w: float, n: int) -> int:
        if not (SEG_Y - 4 <= y <= SEG_Y + SEG_H + 4):
            return -1
        if not (x0 - 4 <= x <= x0 + w * n + 4):
            return -1
        idx = int((max(x0, min(x, x0 + w * n - 1)) - x0) // w)
        return idx if 0 <= idx < n else -1

    def on_click(self, x: float, y: float):
        # 右键菜单打开时，点击必须先处理它（命中菜单项则执行，否则关闭）
        if self._ctx_items:
            hit = self._ctx_hit_item(x, y)
            if hit >= 0:
                self._exec_ctx(hit)
            else:
                self._ctx_items = []
                self.invalidate()
            return
        # 标题栏：搜索框命中优先，其次窗口按钮
        if y < TITLE_H:
            if self._search_box_at(x, y):
                self._search_focus = not self._search_focus
                self.invalidate()
                return
            if self._search_focus:
                self._search_focus = False
                self.invalidate()
            btn = self._tb_button_at(x, y)
            if btn:
                self._pressed_tb = btn
                self.invalidate()
            return
        # 标题栏之外点击：退出搜索输入态
        if self._search_focus:
            self._search_focus = False
            self.invalidate()
        # 视图切换
        idx = self._seg_hit(x, y, PAD, VIEW_SEG_W, len(VIEWS))
        if idx >= 0:
            if idx != self._view_idx:
                self._view_idx = idx
                self._expanded.clear()
                self._scroll = 0
                self._quota_scroll = 0
                self._hover_row = -1
                self.invalidate()
            return
        # 时间范围（额度视图里这一行是说明文字，别误判）
        if self._view_idx != 3:
            idx = self._seg_hit(x, y, PERIOD_SEG_X, PERIOD_SEG_W, len(PERIODS))
            if idx >= 0:
                if idx != self._period_idx:
                    self._period_idx = idx
                    self._expanded.clear()
                    self._scroll = 0
                    self.invalidate()
                return
        # 表格行：点主行展开/收起（额度视图没有表格，别去碰上一屏残留的行）
        # 额度视图没有表格，别去碰上一屏残留的行）
        if self._view_idx == 3:
            return
        i = self._row_at(x, y)
        if i >= 0:
            key = self._rows[i]["key"]
            if key in self._expanded:
                self._expanded.discard(key)
            else:
                self._expanded.add(key)
            self.invalidate()
            return
        # 底部状态点：跳到该工具并展开明细
        for app, dx, dy, dw in self._dot_hit:
            if dy <= y < dy + 18 and dx <= x < dx + dw:
                self._jump_to_app(app)
                return

    def on_click_up(self, x: float = 0.0, y: float = 0.0):
        """标题栏按钮在「抬起」时才生效：必须还在同一个按钮上。"""
        btn = self._pressed_tb
        self._pressed_tb = ""
        if not btn:
            return
        if self._tb_button_at(x, y) != btn:
            self.invalidate()
            return
        self.hide()          # 与原生「关闭」一致：收进托盘，不退出

    def on_nc_hit_test(self, x: float, y: float) -> int:
        """命中测试。顺序有讲究：

        四个角 > 标题栏**按钮** > 边缘缩放热区 > 标题栏空白。

        早前是「标题栏空白优先」，结果整条上边缘都被标题栏吃掉，
        想从上边拖动窗口缩放根本拉不动 —— 边缘热区必须先于标题栏。
        角又排在按钮前面：右上角压着关闭键，让角出来才能四个角都拖得动。
        """
        b = self.resize_border
        w, h = self.width, self.height
        left, right = x <= b, x >= w - b
        top, bottom = y <= b, y >= h - b
        if (top or bottom) and (left or right):
            return super().on_nc_hit_test(x, y)     # 四角：缩放
        if 0 <= y < TITLE_H and self._tb_button_at(x, y):
            return HTCLIENT              # 按钮优先，别被缩放热区吃掉
        if left or right or top or bottom:
            return super().on_nc_hit_test(x, y)     # 边缘：缩放
        if 0 <= y < TITLE_H:
            return HTCAPTION             # 标题栏空白：交给系统拖动窗口
        return super().on_nc_hit_test(x, y)

    def on_resize(self) -> None:
        """窗口尺寸变了：按新尺寸重算所有派生布局。"""
        _relayout(self.width, self.height)
        self._layout_rows()

    def on_mouse_wheel(self, delta: int) -> None:
        if self._view_idx == 3:
            # 额度视图按像素滚动
            self._quota_scroll += delta * QUOTA_STEP
            self._quota_scroll = max(0.0, self._quota_scroll)
        else:
            self._scroll = max(0, min(self._scroll + delta, self._max_scroll()))
        self.invalidate()

    def on_key(self, key: int) -> None:
        """键盘：↑↓/PgUp/PgDn/Home/End 滚动，1-4 切视图；R 手动刷新。"""
        if self._search_focus:
            # 搜索输入中：Esc 退出，其余按键交给 on_char
            if key == 0x1B:
                self._search_focus = False
                self.invalidate()
            return
        if key == 0x52:                            # 'R' 手动扫描刷新
            self._start_scan()
            return
        if 0x31 <= key <= 0x34:                    # '1'..'4'
            idx = key - 0x31
            if idx != self._view_idx:
                self._view_idx = idx
                self._expanded.clear()
                self._scroll = 0
                self._quota_scroll = 0
                self._hover_row = -1
                self.invalidate()
            return
        quota = self._view_idx == 3
        step = QUOTA_STEP
        page = max(1, self._visible_count()) * (step if quota else 1)
        if key == 0x26:            # VK_UP
            d = -1
        elif key == 0x28:          # VK_DOWN
            d = 1
        elif key == 0x21:          # VK_PRIOR / PageUp
            d = -page
        elif key == 0x22:          # VK_NEXT / PageDown
            d = page
        elif key == 0x24:          # VK_HOME
            d = -10 ** 9
        elif key == 0x23:          # VK_END
            d = 10 ** 9
        else:
            return
        if quota:
            self._quota_scroll = max(0.0, self._quota_scroll + d * step)
        else:
            self._scroll = max(0, min(self._scroll + d, self._max_scroll()))
        self.invalidate()

    def on_set_cursor(self, client_pt: tuple[float, float] | None = None) -> bool:
        """分段控件和可展开的行上显示手型光标。"""
        from .win32 import IDC_HAND
        try:
            if client_pt is not None:
                x, y = client_pt
            else:
                pos = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pos))
                user32.ScreenToClient(self.hwnd, ctypes.byref(pos))
                x = pos.x / self.scale
                y = pos.y / self.scale
            hot = self._seg_hit(x, y, PAD, VIEW_SEG_W, len(VIEWS)) >= 0
            if not hot and self._view_idx != 3:
                hot = self._seg_hit(x, y, PERIOD_SEG_X, PERIOD_SEG_W,
                                    len(PERIODS)) >= 0
            if not hot and self._view_idx != 3:
                hot = self._row_at(x, y) >= 0
            if not hot:
                for _app, dx, dy, dw in self._dot_hit:
                    if dy <= y < dy + 18 and dx <= x < dx + dw:
                        hot = True
                        break
            if not hot and self._tb_button_at(x, y):
                hot = True
            if hot:
                user32.SetCursor(user32.LoadCursorW(None, ctypes.c_void_p(IDC_HAND)))
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def on_char(self, ch: str) -> bool:
        """搜索框输入。返回 True 表示已消费。"""
        if not self._search_focus:
            return False
        if ch == "\x08":                       # Backspace
            self._search_q = self._search_q[:-1]
        elif ch == "\r" or ch == "\n":        # Enter：收起键盘焦点，保留过滤词
            self._search_focus = False
        elif ch == "\x1b":                     # Esc：清空并退出
            self._search_q = ""
            self._search_focus = False
        elif ch.isprintable():
            if len(self._search_q) < 48:
                self._search_q += ch
        self._scroll = 0
        self.invalidate()
        return True

    def on_right_click(self, x: float, y: float) -> None:
        """行区域右键：弹出上下文菜单。"""
        if self._ctx_items:
            self._ctx_items = []
            self.invalidate()
            return
        i = self._row_at(x, y)
        if i >= 0:
            self._open_ctx_menu(x, y, self._rows[i])
        else:
            self._ctx_items = []
            self.invalidate()

    def on_hover(self) -> None:
        """鼠标移动时更新悬停行，变化了才重绘（避免每次移动都刷新）。"""
        mx, my = self._mouse_x, self._mouse_y
        if self._ctx_items:
            hot = self._ctx_hit_item(mx, my)
            if hot != self._ctx_hot:
                self._ctx_hot = hot
                self.invalidate()
        new_tb = self._tb_button_at(mx, my)
        if new_tb != self._hover_tb:
            self._hover_tb = new_tb
            self.invalidate()
        if self._view_idx == 3:
            return
        new = self._row_at(mx, my)
        if new != self._hover_row:
            self._hover_row = new
            self.invalidate()

    def on_close(self):
        self.hide()

    def on_timer(self, tid: int):
        if tid == 2:
            self._start_scan()
            return
        if tid == 3:
            self._start_quota()
            return
        if tid == 4:
            self._maybe_sync()
            return
        if self._pending_sync_win:
            # IPC 线程只置了布尔，真正建窗口在这里（UI 线程）
            self._pending_sync_win = False
            cb = self.on_sync_settings_request
            if cb is not None:
                try:
                    cb()
                except Exception:  # noqa: BLE001
                    log.warning("打开同步设置窗口失败", exc_info=True)
        changed = False
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "scan_done":
                    self._status = {r.app: (r.ok, r.error) for r in payload}
                    self._last_update = time.strftime("%H:%M:%S")
                    self._status_error = ""
                    changed = True
                    self._trim_pending = True
                elif kind == "quota_done":
                    self._quota = self._merge_quota(payload)
                    changed = True
                elif kind == "sync_done":
                    self._sync_cfg = syncmod.load_config()
                    self._refresh_sync_note()
                    if not payload.ok and not payload.skipped:
                        log.warning("云同步失败：%s", payload.error)
                    changed = True
                elif kind == "scan_error":
                    changed = True
        except queue.Empty:
            pass
        if changed:
            self.invalidate()
        if self._trim_pending:
            self._trim_pending = False
            trim_working_set()

    def on_tray(self, wparam, lparam):
        if self.tray:
            self.tray.handle(wparam, lparam)

    def on_taskbar_created(self):
        """Explorer 重启后通知区域被清空，把托盘图标放回去。"""
        if self.tray:
            self.tray.recreate()

    def on_show_requested(self):
        self.bring_to_front()
        self.invalidate()