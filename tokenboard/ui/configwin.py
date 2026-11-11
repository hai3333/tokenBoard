"""OpenCode 配置管理窗口。

设计
----
视觉语言跟主面板**同源**（蓝板岩底 + 卡片 + 顶边高光 + 品牌色强调 + 等宽数字），
不是一张「标签 + 输入框」的裸表单：

┌──────────────────────────────────────────────────────────────────┐
│ ▣  OpenCode 配置 │ C:\\...\\opencode.jsonc                   ✕  │  ← 自绘标题栏
├──────────────────┬───────────────────────────────────────────────┤
│ PROVIDERS    5   │ ┌ 基本信息 ──────────────────────────────┐   │
│ ▌火山 Coding Plan │ │ 名称             npm                   │   │
│  hs · ark-95…5bP1│ │ [__________]     [__________________]  │   │
│  6 模型      当前 │ │ baseURL                              │   │
│  …                │ │ [______________________] [拉取模型]   │   │
│                  │ │ APIKey                               │   │
│                  │ │ [________________] [显示] [测试]      │   │
│ [+ 新增] [ 删除 ] │ └────────────────────────────────────────┘   │
│                  │ ┌ 模型 · 6 条 ──────────────────────────┐   │
│                  │ │ [ 多行模型列表 ]                      │   │
│                  │ └────────────────────────────────────────┘   │
│                  │ ┌ 默认模型 [选择器 ▾]     [保存][设为默认]┐  │
├──────────────────┴───────────────────────────────────────────────┤
│ 配置文件：opencode.jsonc          [导入现有配置] [导入 ccswitch]   │
└──────────────────────────────────────────────────────────────────┘

要点：
* 三块右栏（基本信息 / 模型 / 默认模型）**高度按内容分**，不留空白区；
* 「设为默认」是主操作（品牌蓝），其余是次级描边，「删除」是危险色；
* provider 列表用主面板表格同款的**左侧色条 + 选中面**。

输入用**原生 EDIT 子控件**：中文输入法、粘贴、撤销、全选都是系统现成的，
自绘一个输入框要处理的坑多得多。深色主题靠 WM_CTLCOLOREDIT 统一染色。

联网（拉模型目录 / 连通性测试）放在子线程里跑，
界面显示「进行中」并有超时上限，不让用户对着卡死的窗口干等。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from .. import opencode_config as oc
from ..providers import Provider, ProviderStore, models_text, parse_models_text
from .theme import (ACCENT, BASE, DANGER, LINE, LINE_2, OK, SURFACE, SURFACE_2,
                    SURFACE_3, TEXT, TEXT_2, TEXT_3, WARN, mix)
from .win32 import (DT_CENTER, DT_LEFT, DT_RIGHT, DT_SINGLELINE, DT_VCENTER,
                    Font, IDC_HAND, Window, user32)

# ------------------------------------------------------------------ 尺寸（设计像素）
WIN_W = 880
WIN_H = 520
MIN_W = 840
MIN_H = 520

TITLE_H = 36
PAD = 16
GAP = 12
CARD_PAD = 14
LIST_W = 250
BAR_H = 44

HEAD_H = 20          # 卡片内小标题高度
LBL_H = 13           # 字段标签高度
FIELD_H = 28         # 字段框（圆角「井」）的视觉高度
EDIT_H_MIN = 10      # 原生单行 EDIT 自然高度的下限（设计像素）
EDIT_INSET_X = 8     # 原生 EDIT 离井左/右边的距离（避开圆角）
EDIT_INSET_M = 4     # 多行 EDIT 的内缩
ROW_STEP = 48        # 一行字段（标签 + 输入框）占的高度
ROW_H = 48           # 左侧 provider 条目高度
LIST_HEAD = 38       # 列表标题行
LIST_FOOT = 34       # 列表底部按钮行


# 主面板同款卡片材质
CARD_LINE = "#28374F"
CARD_TOP = "#243149"
SHADOW = "#070B13"


class ConfigWindow(Window):
    """OpenCode provider / APIKey 配置管理。"""

    def __init__(self, store: ProviderStore, on_close=None):
        super().__init__("OpenCode 配置", WIN_W, WIN_H, x=200, y=120,
                         class_name="TokenBoardConfigWindow")
        self._bg_color = BASE
        self.min_width = MIN_W
        self.min_height = MIN_H
        self.store = store
        self.on_close_cb = on_close

        self.providers: list[Provider] = []
        self.sel = ""                  # 选中的 provider id
        self.status = ""
        self.status_kind = "info"      # info / ok / warn / err
        self.busy = ""                 # 正在跑的动作名（空 = 空闲）
        self._busy_lock = threading.Lock()
        self._dd_open = False          # 默认模型下拉是否展开
        self._dd_items: list[str] = []
        self._dd_index = -1            # 下拉里当前高亮的项
        self._hover = ""               # 当前悬停的可点区域 key
        self._pressed = ""
        self._list_scroll = 0
        self._show_key = False

        self.f_title = Font(11, 600)
        self.f_sub = Font(9, 400)
        self.f_head = Font(9, 700)
        self.f_label = Font(9, 400)
        self.f_value = Font(10, 400)
        self.f_bold = Font(10, 600)
        self.f_mono = Font(9, 400, name="Consolas")
        self.f_tiny = Font(8, 400)
        self.f_badge = Font(8, 700)
        self.f_btn = Font(9, 400)

        self.edits: dict[str, object] = {}
        self._rects: dict[str, tuple] = {}
        self._edit_h: dict[str, int] = {}   # 单行控件的自然高度（设计像素）

    # ------------------------------------------------------------------ 生命周期
    def create(self):
        super().create()
        self._relayout()
        self._create_edits()
        self.set_timer(200, 1)          # 轮询后台任务 + 刷新
        self.reload()

    def destroy(self):
        for e in self.edits.values():
            try:
                e.destroy()
            except Exception:  # noqa: BLE001
                pass
        self.edits.clear()
        super().destroy()

    def on_close(self):
        self.hide()
        if self.on_close_cb:
            self.on_close_cb()

    # ------------------------------------------------------------------ 布局
    def _relayout(self):
        w, h = self.width, self.height
        content_y = TITLE_H + PAD
        content_h = h - content_y - BAR_H - PAD

        list_x, list_w = PAD, LIST_W
        col_x = list_x + list_w + 14
        col_w = w - col_x - PAD

        # 右栏三块：基本信息（固定）/ 模型（吃掉剩余高度）/ 默认模型（固定）
        info_h = 182
        def_h = 46
        models_h = max(120, content_h - info_h - GAP * 2 - def_h)

        # 左栏：列表卡片 = 标题行 + 条目区 + 底部按钮行
        items_y = content_y + LIST_HEAD
        items_h = content_h - LIST_HEAD - LIST_FOOT

        self._rects = {
            # 左
            "list": (list_x, content_y, list_w, content_h),
            "list_head": (list_x + 14, content_y + 13, 120, 16),
            "list_items": (list_x, items_y, list_w, items_h),
            "btn_add": (list_x + 14, content_y + content_h - 30, 68, 24),
            "btn_del": (list_x + 14 + 74, content_y + content_h - 30, 68, 24),
            # 右
            "card_info": (col_x, content_y, col_w, info_h),
            "card_models": (col_x, content_y + info_h + GAP, col_w, models_h),
            "card_default": (col_x, content_y + info_h + GAP + models_h + GAP,
                             col_w, def_h),
            # 标题栏 / 底栏
            "btn_close": (w - 44, 0, 44, TITLE_H),
            "status": (PAD, h - BAR_H, w - PAD * 2, BAR_H),
            "btn_imp_cc": (w - PAD - 104, h - BAR_H + 9, 104, 26),
            "btn_imp_cfg": (w - PAD - 104 - 8 - 104, h - BAR_H + 9, 104, 26),
        }

        # ---- 基本信息卡：标签在上、输入框在下（两列网格）
        fx = col_x + CARD_PAD
        fw = col_w - CARD_PAD * 2
        fy = content_y + CARD_PAD + HEAD_H + 8
        self._rects["lbl_name"] = (fx, fy, 120, LBL_H)
        self._rects["f_name"] = (fx, fy + 15, 196, FIELD_H)
        self._rects["lbl_npm"] = (fx + 214, fy, 120, LBL_H)
        self._rects["f_npm"] = (fx + 214, fy + 15, fw - 214, FIELD_H)

        y2 = fy + ROW_STEP
        self._rects["lbl_base"] = (fx, y2, 120, LBL_H)
        self._rects["f_base"] = (fx, y2 + 15, fw - 100, FIELD_H)
        self._rects["btn_fetch"] = (fx + fw - 90, y2 + 15, 90, FIELD_H)

        y3 = fy + ROW_STEP * 2
        self._rects["lbl_key"] = (fx, y3, 120, LBL_H)
        self._rects["f_key"] = (fx, y3 + 15, fw - 132, FIELD_H)
        self._rects["btn_show"] = (fx + fw - 122, y3 + 17, 52, 24)
        self._rects["btn_test"] = (fx + fw - 64, y3 + 17, 64, 24)

        # ---- 模型卡
        my = content_y + info_h + GAP
        mh = models_h
        self._rects["models_label"] = (col_x + CARD_PAD, my + CARD_PAD, 220, 16)
        self._rects["models_hint"] = (col_x + col_w - CARD_PAD - 260, my + CARD_PAD,
                                      260, 16)
        self._rects["f_models"] = (col_x + CARD_PAD,
                                   my + CARD_PAD + HEAD_H + 4,
                                   fw, mh - CARD_PAD * 2 - HEAD_H - 4)

        # ---- 默认模型卡
        dy = content_y + info_h + GAP + mh + GAP
        self._rects["f_default_label"] = (col_x + CARD_PAD, dy + 15, 60, 16)
        self._rects["f_default"] = (col_x + CARD_PAD + 66, dy + 9, 300, 28)
        self._rects["btn_save"] = (col_x + col_w - CARD_PAD - 92 - 8 - 76, dy + 9,
                                   76, 28)
        self._rects["btn_apply"] = (col_x + col_w - CARD_PAD - 92, dy + 9, 92, 28)

    def _create_edits(self):
        e = self.edits
        e["name"] = self.create_edit(0, 0, 10, 10, font=self.f_value)
        e["base"] = self.create_edit(0, 0, 10, 10, font=self.f_value)
        e["key"] = self.create_edit(0, 0, 10, 10, password=True, font=self.f_value)
        e["npm"] = self.create_edit(0, 0, 10, 10, font=self.f_mono)
        e["models"] = self.create_edit(0, 0, 10, 10, multiline=True, font=self.f_mono)
        # 量一次单行 EDIT 的自然高度（字高 + 行外距），换算成设计像素。
        # 原生单行 EDIT 是从客户区顶部往下画字的，框给高了字就浮在上面，
        # 所以这个高度必须准，不能拍脑袋。
        for name, font in (("name", self.f_value), ("base", self.f_value),
                           ("key", self.f_value), ("npm", self.f_mono)):
            th, el = font.metrics(self.scale)
            self._edit_h[name] = max(EDIT_H_MIN, int(round((th + el) / self.scale)))
        self._apply_edits()

    def _apply_edits(self):
        """把布局算出来的位置同步给原生控件（缩放窗口后要重算）。"""
        sc = self.scale
        # 单行字段：原生 EDIT 用自然高度，水平内缩、垂直居中放进圆角「井」里
        for name, key in (("name", "f_name"), ("base", "f_base"),
                          ("key", "f_key"), ("npm", "f_npm")):
            r = self._rects.get(key)
            e = self.edits.get(name)
            if not r or not e:
                continue
            x, y, w, h = r
            eh = self._edit_h.get(name, EDIT_H_MIN)
            e.set_rect(int((x + EDIT_INSET_X) * sc),
                       int((y + (h - eh) / 2) * sc),
                       int((w - EDIT_INSET_X * 2) * sc),
                       int(eh * sc))
        # 多行模型框：铺满圆角框（内缩一圈，免得直角盖住圆角）
        r = self._rects.get("f_models")
        e = self.edits.get("models")
        if r and e:
            x, y, w, h = r
            e.set_rect(int((x + EDIT_INSET_M) * sc),
                       int((y + EDIT_INSET_M) * sc),
                       int((w - EDIT_INSET_M * 2) * sc),
                       int((h - EDIT_INSET_M * 2) * sc))

    def on_resize(self):
        self._relayout()
        self._apply_edits()

    # ------------------------------------------------------------------ 数据
    def reload(self):
        self.providers = self.store.list()
        # 库里还没记全局默认模型时，从配置文件里读一次（只读，不写文件）：
        # 不然界面上「当前生效」和「全局默认」永远是空的，看着像配置没生效。
        if not self.store.default_model():
            try:
                cfg = oc.read(self.store.config_path)
                self.store.adopt_global_model(cfg.get("model") or "")
                self.providers = self.store.list()
            except Exception:  # noqa: BLE001
                pass
        if self.sel and not any(p.id == self.sel for p in self.providers):
            self.sel = ""
        if not self.sel:
            cur = self.store.current()
            self.sel = cur.id if cur else (self.providers[0].id if self.providers else "")
        self._load_form()
        self.invalidate()

    def _current(self) -> Provider | None:
        for p in self.providers:
            if p.id == self.sel:
                return p
        return None

    def _load_form(self):
        p = self._current()
        e = self.edits
        if not p:
            for k in ("name", "base", "key", "npm"):
                e[k].set_text("")
            e["models"].set_text("")
            return
        e["name"].set_text(p.name)
        e["base"].set_text(p.base_url)
        e["key"].set_text(p.api_key)
        e["npm"].set_text(p.npm)
        self._set_models_text(models_text(p))

    def _set_models_text(self, text: str):
        """多行编辑框要用 CRLF 换行 —— 只给 \\n 的话 Windows 会当成普通字符，
        所有模型会挤在同一行。"""
        self.edits["models"].set_text((text or "").replace("\r\n", "\n").replace("\n", "\r\n"))

    def _form_to_provider(self) -> Provider:
        """把表单内容收集成一个 Provider（还没落库）。"""
        p = self._current()
        e = self.edits
        pid = p.id if p else ""
        return Provider(
            id=pid,
            name=e["name"].get_text().strip(),
            npm=e["npm"].get_text().strip() or oc.DEFAULT_NPM,
            base_url=e["base"].get_text().strip(),
            api_key=e["key"].get_text().strip(),
            models=parse_models_text(e["models"].get_text()),
            default_model=(p.default_model if p else ""),
            is_current=(p.is_current if p else False),
            sort_index=(p.sort_index if p else len(self.providers)),
        )

    def _set_status(self, text: str, kind: str = "info"):
        self.status = text
        self.status_kind = kind
        self.invalidate()

    # ------------------------------------------------------------------ 绘制
    def draw(self, c):
        """基类 on_paint 负责建画布 + blit，这里只画内容。

        （早前错写成覆盖 on_paint：基类的 on_paint 才是创建画布并 blit 的地方，
        覆盖掉之后整个窗口自绘全没了，只剩原生输入框浮在黑底上。）
        """
        c.fill(BASE)
        self._draw_title(c)
        self._draw_list(c)
        self._draw_info(c)
        self._draw_models(c)
        self._draw_default(c)
        self._draw_status(c)
        if self._dd_open:
            self._draw_dropdown(c)

    # ---- 通用件 --------------------------------------------------------
    @staticmethod
    def _card(c, x, y, w, h, r=12):
        """卡片材质：投影 + 面 + 描边 + 顶边高光（和主面板同一套）。"""
        c.round_rect(x, y + 1.5, w, h, r, fill=SHADOW)
        c.round_rect(x, y, w, h, r, fill=SURFACE, stroke=CARD_LINE, stroke_w=1.0)
        c.line(x + r, y + 1, x + w - r, y + 1, CARD_TOP, 1)

    def _section(self, c, x, y, w, title, right=""):
        """卡片内的小标题：左边一条品牌色竖条 + 标题，右侧可选说明。"""
        c.round_rect(x, y + 2, 2.5, 11, 1.2, fill=ACCENT)
        c.text(x + 9, y, 240, 16, title, self.f_head, TEXT_2,
               align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        if right:
            c.text(x, y, w, 16, right, self.f_sub, TEXT_3,
                   align=DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

    @staticmethod
    def _pill(c, x, y, text, color, font, pad=6, h=15):
        """小圆角标签（数量、状态徽标）。"""
        tw, _ = c.measure(text, font)
        w = tw + pad * 2
        c.round_rect(x, y, w, h, h / 2, fill=mix(SURFACE, color, 0.20),
                     stroke=mix(SURFACE, color, 0.42), stroke_w=1.0)
        c.text(x, y, w, h, text, font, color,
               align=DT_CENTER | DT_VCENTER | DT_SINGLELINE)
        return w

    # ---- 标题栏 --------------------------------------------------------
    def _draw_title(self, c):
        # 和主面板同一套图标：圆角小方块 + 三根递增柱
        ix, iy, isz = PAD, (TITLE_H - 20) / 2, 20
        c.round_rect(ix, iy, isz, isz, 6, fill=mix(SURFACE_2, ACCENT, 0.16),
                     stroke=mix(SURFACE_2, ACCENT, 0.32), stroke_w=1.0)
        for i, (bh, col) in enumerate([(4, "#4E5B78"), (7, "#7C93C7"), (10, ACCENT)]):
            c.round_rect(ix + 5 + i * 4, iy + 10 - bh, 3, bh, 1.5, fill=col)
        tx = ix + isz + 8
        c.text(tx, 0, 200, TITLE_H, "OpenCode 配置", self.f_title, TEXT,
               align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        # 竖分隔 + 配置文件路径（分隔线按标题实测宽度放，别写死）
        tw, _ = c.measure("OpenCode 配置", self.f_title)
        sep = tx + max(80, tw + 14)
        c.line(sep, TITLE_H / 2 - 5, sep, TITLE_H / 2 + 5, LINE_2, 1)
        c.text(sep + 12, 0, 420, TITLE_H, str(self.store.config_path),
               self.f_mono, TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

        # 关闭按钮（悬停变红，和主面板一致）
        r = self._rects["btn_close"]
        hot = self._hover == "btn_close"
        if hot:
            c.fill_rect(r[0], 0, r[2], TITLE_H, "#E5484D")
        gcol = "#FFFFFF" if hot else TEXT_2
        cx = r[0] + r[2] / 2
        cy = TITLE_H / 2
        c.line(cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5, gcol, 1)
        c.line(cx + 4.5, cy - 4.5, cx - 4.5, cy + 4.5, gcol, 1)
        c.line(0, TITLE_H - 1, self.width, TITLE_H - 1, LINE)

    # ---- 左：provider 列表 ----------------------------------------------
    def _draw_list(self, c):
        x, y, w, h = self._rects["list"]
        self._card(c, x, y, w, h)

        hx, hy, hw, hh = self._rects["list_head"]
        c.text(hx, hy, hw, hh, "PROVIDERS", self.f_head, TEXT_2,
               align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        # 数量药丸，右对齐
        cnt = f"{len(self.providers)}"
        tw, _ = c.measure(cnt, self.f_tiny)
        self._pill(c, x + w - 16 - (tw + 12), y + 13, cnt, ACCENT, self.f_tiny)

        # 条目区
        ix, iy, iw, ih = self._rects["list_items"]
        if not self.providers:
            c.text(x + 16, iy + 18, w - 32, 60,
                   "还没有 provider\n点下方「新增」手工建一个，\n或从底部「导入现有配置」导入",
                   self.f_sub, TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        else:
            rows = max(1, int(ih // ROW_H))
            max_scroll = max(0, len(self.providers) - rows)
            self._list_scroll = max(0, min(self._list_scroll, max_scroll))
            for i in range(rows):
                idx = self._list_scroll + i
                if idx >= len(self.providers):
                    break
                p = self.providers[idx]
                ry = iy + i * ROW_H
                sel = p.id == self.sel
                if sel:
                    c.round_rect(x + 8, ry, w - 16, ROW_H - 4, 8, fill=SURFACE_3)
                    # 左侧品牌色条：和主面板表格同一套语言
                    c.round_rect(x + 8, ry + 9, 2.5, ROW_H - 22, 1.2, fill=ACCENT)
                elif self._hover == f"row_{p.id}":
                    c.round_rect(x + 8, ry, w - 16, ROW_H - 4, 8, fill=SURFACE_2)

                tx = x + 20
                name = p.name or p.id
                right_x = x + w - 16
                if p.is_current:
                    # 「当前生效」徽标贴右，标题按剩下的宽度排
                    bw, _ = c.measure("当前", self.f_badge)
                    bw += 10
                    self._pill(c, right_x - bw, ry + 6, "当前", OK, self.f_badge,
                               pad=5, h=13)
                    right_x -= bw + 8
                c.text(tx, ry + 5, right_x - tx, 16, name,
                       self.f_bold if sel else self.f_value,
                       TEXT if sel else TEXT_2,
                       align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

                sub = f"{p.id}  ·  {p.masked_key or '未设密钥'}"
                c.text(tx, ry + 24, w - 100, 14, sub, self.f_mono, TEXT_3,
                       align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
                n = len(p.model_ids())
                c.text(x + w - 66, ry + 24, 50, 14, f"{n} 模型", self.f_tiny, TEXT_3,
                       align=DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

        # 底部：新增 / 删除
        c.line(x + 14, y + h - LIST_FOOT, x + w - 14, y + h - LIST_FOOT, LINE, 1)
        self._button(c, "btn_add", "新增", "btn_add")
        self._button(c, "btn_del", "删除", "btn_del", danger=True)

    # ---- 右：基本信息 --------------------------------------------------
    def _draw_info(self, c):
        cx, cy, cw, ch = self._rects["card_info"]
        self._card(c, cx, cy, cw, ch)
        self._section(c, cx + CARD_PAD, cy + CARD_PAD, cw - CARD_PAD * 2,
                      "基本信息")
        # 先画输入框的「井」：原生 EDIT 是子窗口，永远盖在父窗口绘制之上，
        # 框只能自绘（填充色必须和 edit_bg_color 一致，才看不出接缝）。
        for key in ("f_name", "f_npm", "f_base", "f_key"):
            self._well(c, self._rects[key])
        for key, label in (("lbl_name", "名称"), ("lbl_npm", "npm"),
                           ("lbl_base", "baseURL"), ("lbl_key", "APIKey")):
            r = self._rects[key]
            c.text(r[0], r[1], r[2], r[3], label, self.f_label, TEXT_3,
                   align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        self._button(c, "btn_fetch", "拉取模型", "btn_fetch")
        self._button(c, "btn_show", "显示" if not self._show_key else "隐藏",
                     "btn_show")
        self._button(c, "btn_test", "测试", "btn_test")

    def _well(self, c, r):
        """输入框的底：圆角 + 描边。填充色要和 EDIT 的背景色一模一样。"""
        if not r:
            return
        x, y, w, h = r
        c.round_rect(x, y, w, h, 6, fill=SURFACE_2, stroke=LINE_2, stroke_w=1)

    # ---- 右：模型 ------------------------------------------------------
    def _draw_models(self, c):
        cx, cy, cw, ch = self._rects["card_models"]
        self._card(c, cx, cy, cw, ch)
        self._well(c, self._rects["f_models"])
        lr = self._rects["models_label"]
        p = self._current()
        n = len(p.model_ids()) if p else 0
        c.round_rect(lr[0], lr[1] + 2, 2.5, 11, 1.2, fill=ACCENT)
        c.text(lr[0] + 9, lr[1], 220, lr[3], f"模型 · {n} 条", self.f_head, TEXT_2,
               align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        hr = self._rects["models_hint"]
        c.text(hr[0], hr[1], hr[2], hr[3], "一行一个：模型id  显示名（留空不限制）",
               self.f_sub, TEXT_3, align=DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

    # ---- 右：默认模型 + 操作 --------------------------------------------
    def _draw_default(self, c):
        cx, cy, cw, ch = self._rects["card_default"]
        self._card(c, cx, cy, cw, ch)
        lr = self._rects["f_default_label"]
        c.text(lr[0], lr[1], lr[2], lr[3], "默认模型", self.f_label, TEXT_3,
               align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        self._draw_default_picker(c)
        self._button(c, "btn_save", "保存", "btn_save")
        self._button(c, "btn_apply", "设为默认", "btn_apply", primary=True)

    def _draw_default_picker(self, c):
        x, y, w, h = self._rects["f_default"]
        p = self._current()
        cur = p.default_model if p else ""
        c.round_rect(x, y, w, h, 6, fill=SURFACE_2, stroke=LINE_2, stroke_w=1)
        label = cur or "（未设置）"
        c.text(x + 10, y, w - 40, h, label, self.f_value,
               TEXT if cur else TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        c.text(x + w - 30, y, 24, h, "▾", self.f_value, TEXT_2,
               align=DT_CENTER | DT_VCENTER | DT_SINGLELINE)

    def _draw_dropdown(self, c):
        x, y, w, h = self._rects["f_default"]
        items = self._dd_items
        row_h = 24
        dh = min(len(items), 8) * row_h + 8
        dx, dy = x, y + h + 4
        c.round_rect(dx, dy, w, dh, 8, fill=SURFACE_3, stroke=LINE_2, stroke_w=1)
        if not items:
            c.text(dx + 10, dy + 6, w - 20, row_h, "这个 provider 还没有模型",
                   self.f_sub, TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
            return
        for i, mid in enumerate(items[:8]):
            iy = dy + 4 + i * row_h
            if i == self._dd_index:
                c.round_rect(dx + 4, iy, w - 8, row_h, 5, fill=SURFACE_2)
            c.text(dx + 12, iy, w - 24, row_h, mid, self.f_mono, TEXT,
                   align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

    # ---- 底栏 ----------------------------------------------------------
    def _draw_status(self, c):
        x, y, w, h = self._rects["status"]
        c.line(PAD, y - 8, self.width - PAD, y - 8, LINE)
        color = {"ok": OK, "warn": WARN, "err": DANGER}.get(self.status_kind, TEXT_3)
        text = self.status
        if self.busy:
            text = f"⏳ {self.busy}…（最多等 20 秒）"
        # 左：配置文件名
        c.text(x, y, 130, h, f"配置文件：{self.store.config_path.name}", self.f_sub,
               TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        # opencode 现在实际生效的全局默认模型（不然界面上看不出哪个在用）
        gm = self.store.default_model()
        sx = x + 138
        if gm:
            txt = f"全局默认：{gm}"
            c.text(sx, y, 320, h, txt, self.f_mono, TEXT_3,
                   align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
            sx += c.measure(txt, self.f_mono)[0] + 10
            # 全局默认指向的 provider 不在库里时要说一句：
            # 不然左栏一个「当前」徽标都没有，看着像功能坏了。
            pid = gm.split("/", 1)[0]
            if pid and not any(p.id == pid for p in self.providers):
                c.text(sx, y, 140, h, "（provider 不在库中）", self.f_sub, WARN,
                       align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
                sx += 118
        # 状态信息
        if text:
            sx = max(sx + 10, x + 356)
            c.text(sx, y, w - (sx - x) - 232, h, text, self.f_value, color,
                   align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        self._button(c, "btn_imp_cfg", "导入现有配置", "btn_imp_cfg")
        self._button(c, "btn_imp_cc", "导入 ccswitch", "btn_imp_cc")

    def _button(self, c, key, text, hkey, primary=False, danger=False):
        r = self._rects.get(key)
        if not r:
            return
        x, y, w, h = r
        hot = self._hover == hkey
        pressed = self._pressed == hkey
        if primary:
            fill = ACCENT if not hot else mix(ACCENT, "#FFFFFF", 0.18)
            fg = "#0C1220"
            stroke = None
        elif danger:
            fill = mix(SURFACE, DANGER, 0.22) if (hot or pressed) else SURFACE_2
            fg = DANGER if hot else TEXT_2
            stroke = mix(SURFACE, DANGER, 0.40) if hot else LINE_2
        else:
            fill = SURFACE_3 if (hot or pressed) else SURFACE_2
            fg = TEXT if hot else TEXT_2
            stroke = LINE_2
        c.round_rect(x, y, w, h, 6, fill=fill, stroke=stroke, stroke_w=1)
        c.text(x, y, w, h, text, self.f_btn, fg,
               align=DT_CENTER | DT_VCENTER | DT_SINGLELINE)

    # ------------------------------------------------------------------ 交互
    def _in(self, key, x, y) -> bool:
        r = self._rects.get(key)
        if not r:
            return False
        rx, ry, rw, rh = r
        return rx <= x < rx + rw and ry <= y < ry + rh

    def on_hover(self):
        x, y = self._mouse_x, self._mouse_y
        hot = ""
        if self._in("btn_close", x, y):
            hot = "btn_close"
        elif self._in("btn_add", x, y):
            hot = "btn_add"
        elif self._in("btn_del", x, y):
            hot = "btn_del"
        elif self._in("btn_fetch", x, y):
            hot = "btn_fetch"
        elif self._in("btn_show", x, y):
            hot = "btn_show"
        elif self._in("btn_test", x, y):
            hot = "btn_test"
        elif self._in("btn_save", x, y):
            hot = "btn_save"
        elif self._in("btn_apply", x, y):
            hot = "btn_apply"
        elif self._in("btn_imp_cfg", x, y):
            hot = "btn_imp_cfg"
        elif self._in("btn_imp_cc", x, y):
            hot = "btn_imp_cc"
        elif self._in("f_default", x, y):
            hot = "f_default"
        elif self._dd_open:
            hot = ""
        else:
            hot = self._list_row_at(x, y) or ""
        if hot != self._hover:
            self._hover = hot
            self.invalidate()

    def _list_row_at(self, x, y) -> str:
        lx, ly, lw, lh = self._rects["list_items"]
        if not (lx <= x < lx + lw and ly <= y < ly + lh):
            return ""
        idx = int((y - ly) // ROW_H) + self._list_scroll
        if 0 <= idx < len(self.providers):
            return f"row_{self.providers[idx].id}"
        return ""

    def on_click(self, x: float, y: float):
        self._pressed = self._hover
        # 下拉展开时，优先处理下拉里的选择
        if self._dd_open:
            if self._pick_dropdown(x, y):
                return
            self._dd_open = False
            self.invalidate()
            return

        if self._in("btn_close", x, y):
            self.on_close()
            return
        if self._in("btn_add", x, y):
            self._add_provider()
            return
        if self._in("btn_del", x, y):
            self._delete_provider()
            return
        if self._in("btn_fetch", x, y):
            self._fetch_models()
            return
        if self._in("btn_show", x, y):
            self._show_key = not self._show_key
            self.edits["key"].set_password_char("" if self._show_key else "•")
            self.invalidate()
            return
        if self._in("btn_test", x, y):
            self._test_connection()
            return
        if self._in("btn_save", x, y):
            self._save_provider()
            return
        if self._in("btn_apply", x, y):
            self._save_provider(apply_default=True)
            return
        if self._in("btn_imp_cfg", x, y):
            self._import_from_config()
            return
        if self._in("btn_imp_cc", x, y):
            self._import_from_ccswitch()
            return
        if self._in("f_default", x, y):
            p = self._current()
            self._dd_items = p.model_ids() if p else []
            self._dd_index = self._dd_items.index(p.default_model) \
                if p and p.default_model in self._dd_items else -1
            self._dd_open = True
            self.invalidate()
            return

        row = self._list_row_at(x, y)
        if row:
            pid = row[4:]
            if pid != self.sel:
                self.sel = pid
                self._load_form()
                self.invalidate()
            return

    def on_click_up(self, x: float = 0.0, y: float = 0.0):
        self._pressed = ""

    def _pick_dropdown(self, x, y) -> bool:
        dx, dy, dw, _ = self._rects["f_default"]
        row_h = 24
        top = dy + 4
        if not (dx <= x < dx + dw and top <= y < top + 8 * row_h):
            return False
        idx = int((y - top) // row_h)
        if 0 <= idx < len(self._dd_items):
            mid = self._dd_items[idx]
            self._dd_open = False
            self._dd_index = -1
            p = self._current()
            if p:
                p.default_model = mid
                self.store.save(p)
                self.providers = self.store.list()
                self.invalidate()
                self._set_status(f"已把 {mid} 设为 {p.id} 的默认模型（还要点「设为默认」才会写进 opencode.jsonc）",
                                 "ok")
            return True
        return False

    def on_key(self, key: int):
        if key == 0x1B:            # ESC：先关下拉，再关窗口
            if self._dd_open:
                self._dd_open = False
                self.invalidate()
            else:
                self.on_close()
        elif key == 0x0D:          # Enter：保存
            self._save_provider()
        elif key == 0x2E and self._mouse_x < self._rects["list"][0] + self._rects["list"][2]:
            self._delete_provider()

    def on_mouse_wheel(self, delta: int):
        ix, iy, iw, ih = self._rects["list_items"]
        rows = max(1, int(ih // ROW_H))
        max_scroll = max(0, len(self.providers) - rows)
        self._list_scroll = max(0, min(self._list_scroll - delta, max_scroll))
        self.invalidate()

    # ------------------------------------------------------------------ 动作
    def _add_provider(self):
        pid = f"provider{len(self.providers) + 1}"
        base = pid
        i = 1
        existing = {p.id for p in self.providers}
        while pid in existing:
            i += 1
            pid = f"{base}{i}"
        p = Provider(id=pid, name="新建 provider", npm=oc.DEFAULT_NPM,
                     base_url="", api_key="", models={}, sort_index=len(self.providers))
        self.store.save(p)
        self.sel = pid
        self.reload()
        self._set_status(f"已新增 {pid}，填完点「保存」", "info")
        self.edits["name"].focus()

    def _delete_provider(self):
        p = self._current()
        if not p:
            self._set_status("先在左边选一个 provider", "warn")
            return
        self.store.delete(p.id)
        self.sel = ""
        self.reload()
        self._set_status(f"已删除 {p.id}（还没写回 opencode.jsonc，点「设为默认」会同步）", "ok")

    def _save_provider(self, apply_default: bool = False):
        p = self._form_to_provider()
        if not p.id:
            self._set_status("没有选中的 provider", "warn")
            return
        if not p.base_url:
            self._set_status("baseURL 不能为空", "warn")
            return
        self.store.save(p)
        self.providers = self.store.list()
        if apply_default:
            mid = p.default_model or (p.model_ids()[0] if p.model_ids() else "")
            if not mid:
                self._set_status("这个 provider 还没有模型，无法设为默认", "warn")
                return
            try:
                # switch_to 会做三件事：标当前、写全局默认模型、写 opencode.jsonc
                value = self.store.switch_to(p.id, mid)
            except OSError as e:
                self._set_status(f"写 opencode.jsonc 失败：{e}", "err")
                return
            self._set_status(f"已保存并设为默认：{value}（已写入 opencode.jsonc）", "ok")
        else:
            self._set_status(f"已保存 {p.id}", "ok")
        self.invalidate()

    def _import_from_config(self):
        try:
            n = self.store.import_from_opencode_config()
        except OSError as e:
            self._set_status(f"导入失败：{e}", "err")
            return
        self.reload()
        self._set_status(f"从 {self.store.config_path.name} 导入了 {n} 个 provider"
                         if n else "配置文件里没有 provider 可导入", "ok" if n else "warn")

    def _import_from_ccswitch(self):
        try:
            n = self.store.import_from_ccswitch()
        except FileNotFoundError as e:
            self._set_status(f"没找到 ccswitch：{e}", "warn")
            return
        except Exception as e:  # noqa: BLE001
            self._set_status(f"导入 ccswitch 失败：{e}", "err")
            return
        self.reload()
        self._set_status(f"从 ccswitch 导入了 {n} 个 provider", "ok" if n else "warn")

    # ---------------------------------------------------------- 后台联网
    def _run_bg(self, label: str, fn):
        """联网动作统一放后台跑，界面显示进行中。"""
        if self.busy:
            self._set_status(f"「{self.busy}」还在跑，先等它结束", "warn")
            return
        self.busy = label
        # 坑：清空结果必须在**起线程之前**。
        # 放在后面的话，线程跑得太快（本地/mock 服务毫秒级返回），
        # 结果刚写进去就被这里的 None 抹掉，界面永远等不到回应。
        self._bg_result = None

        def work():
            try:
                result = fn()
            except Exception as e:  # noqa: BLE001
                result = (False, str(e))
            with self._busy_lock:
                self._bg_result = result
                self.busy = ""

        threading.Thread(target=work, daemon=True).start()
        self.invalidate()

    def _fetch_models(self):
        p = self._form_to_provider()
        if not p.base_url:
            self._set_status("先填 baseURL", "warn")
            return

        def job():
            ids, err = oc.fetch_models(p.base_url, p.api_key, timeout=12)
            return ("models", ids, err)

        self._run_bg("拉取模型", job)

    def _test_connection(self):
        p = self._form_to_provider()
        if not p.base_url:
            self._set_status("先填 baseURL", "warn")
            return
        mid = p.default_model or (p.model_ids()[0] if p.model_ids() else "")
        if not mid:
            self._set_status("先选一个模型再测试", "warn")
            return

        def job():
            return oc.test_connection(p.base_url, p.api_key, mid, timeout=20)

        self._run_bg(f"测试 {mid}", job)

    def on_timer(self, tid: int):
        with self._busy_lock:
            result = getattr(self, "_bg_result", None)
            if result is not None:
                self._bg_result = None
        if result is None:
            return
        if len(result) == 3:        # 拉模型
            _, ids, err = result
            if err and not ids:
                self._set_status(f"拉模型失败：{err}", "err")
            elif not ids:
                self._set_status("这个地址没返回模型列表", "warn")
            else:
                self._set_models_text(
                    "\n".join(f"{mid} {mid}" for mid in ids))
                self._set_status(f"拉到 {len(ids)} 个模型，已填进模型框（点保存生效）", "ok")
        else:                       # 连通性测试
            ok, msg = result
            self._set_status(("✓ " if ok else "✗ ") + msg, "ok" if ok else "err")
        self.invalidate()
