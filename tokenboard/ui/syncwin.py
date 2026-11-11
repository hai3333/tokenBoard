"""WebDAV 云同步设置窗口。

视觉语言和主面板同源：蓝板岩底 + 卡片 + 顶边高光 + 等宽数字。
输入框用原生 EDIT（中文输入法 / 粘贴 / 撤销都是系统现成的），
深色主题靠父窗口的 WM_CTLCOLOREDIT 统一染色。

结构：

    ┌ TokenBoard 云同步 · WebDAV                              ✕ ┐
    │ ┌ 服务器 ───────────────────────────────────────────────┐ │
    │ │ 地址 [https://dav.example.com/dav        ] [测试连接] │ │
    │ │ 用户名 [____]   密码 [••••••••]  [显示]               │ │
    │ │ 远程目录 [TokenBoard]   同步间隔 [30] 分钟            │ │
    │ └───────────────────────────────────────────────────────┘ │
    │ ┌ 状态 ─────────────────────────────────────────────────┐ │
    │ │ ● 已启用 · 每 30 分钟自动同步       上次同步 11:20    │ │
    │ │ 本地 12,345 条 · 远端 13,000 条 / 2.3 MB              │ │
    │ │ （错误信息，红色）                                     │ │
    │ └───────────────────────────────────────────────────────┘ │
    │ ┌ 说明 ─────────────────────────────────────────────────┐ │
    │ │ 只传用量与速度采样，不含任何 API Key。差异按请求 id    │ │
    │ │ 合并，重复同步不会把数字刷大。                          │ │
    │ └───────────────────────────────────────────────────────┘ │
    │ [✓] 启用云同步                    [立即同步] [保存并关闭] │
    └───────────────────────────────────────────────────────────┘

联网（测试连接 / 立即同步）都在子线程里跑，界面显示「进行中」，
不让用户对着卡死的窗口干等。
"""
from __future__ import annotations

import threading
import time

from .. import sync as syncmod
from ..sync import SyncConfig
from .theme import (ACCENT, BASE, DANGER, LINE, LINE_2, OK, SURFACE, SURFACE_2,
                    SURFACE_3, TEXT, TEXT_2, TEXT_3, WARN, mix)
from .win32 import (DT_CENTER, DT_LEFT, DT_RIGHT, DT_SINGLELINE, DT_VCENTER,
                    HTCAPTION, HTCLIENT, Font, Window)

# ---------------------------------------------------------------- 尺寸（设计像素）
WIN_W = 880
WIN_H = 560
MIN_W = 820
MIN_H = 520

TITLE_H = 36
PAD = 16
GAP = 12
CARD_PAD = 14
HEAD_H = 20
LBL_H = 13
FIELD_H = 28
EDIT_H_MIN = 10
EDIT_INSET_X = 8
ROW_STEP = 52
BAR_H = 56

CARD_LINE = "#28374F"
CARD_TOP = "#243149"
SHADOW = "#070B13"


def _fmt_ts(ms: int) -> str:
    if not ms:
        return "从未"
    t = time.localtime(ms / 1000)
    today = time.strftime("%Y-%m-%d", time.localtime())
    if time.strftime("%Y-%m-%d", t) == today:
        return time.strftime("%H:%M", t)
    return time.strftime("%m-%d %H:%M", t)


def _ago(ms: int) -> str:
    if not ms:
        return ""
    sec = max(0, int(time.time() - ms / 1000))
    if sec < 60:
        return "刚刚"
    if sec < 3600:
        return f"{sec // 60} 分钟前"
    if sec < 86400:
        return f"{sec // 3600} 小时前"
    return f"{sec // 86400} 天前"


def _fmt_size(n: int) -> str:
    n = float(n or 0)
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{int(n)} B"


class SyncWindow(Window):
    """WebDAV 同步设置。"""

    def __init__(self, store, on_changed=None):
        super().__init__("TokenBoard 云同步", WIN_W, WIN_H, x=220, y=140,
                         class_name="TokenBoardSyncWindow")
        self._bg_color = BASE
        self.min_width = MIN_W
        self.min_height = MIN_H
        self.store = store
        self.on_changed = on_changed

        self.cfg: SyncConfig = syncmod.load_config()
        self.status = ""
        self.status_kind = "info"      # info / ok / warn / err
        self.busy = ""                 # 正在跑的动作名
        self._busy_lock = threading.Lock()
        self._bg_result = None
        self._hover = ""
        self._show_key = False
        self._enabled = bool(self.cfg.enabled)

        self.f_title = Font(11, 600)
        self.f_head = Font(9, 700)
        self.f_label = Font(9, 400)
        self.f_value = Font(10, 400)
        self.f_mono = Font(9, 400, name="Consolas")
        self.f_tiny = Font(8, 400)
        self.f_btn = Font(9, 400)

        self.edits: dict[str, object] = {}
        self._rects: dict[str, tuple] = {}
        self._edit_h: dict[str, int] = {}

    # ------------------------------------------------------------------ 生命周期
    def create(self):
        super().create()
        self._relayout()
        self._create_edits()
        self.set_timer(200, 1)
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

    # ------------------------------------------------------------------ 布局
    def _relayout(self):
        w, h = self.width, self.height
        content_w = w - PAD * 2

        info_h = CARD_PAD + HEAD_H + 8 + ROW_STEP * 2 + FIELD_H + CARD_PAD
        status_h = 132
        note_h = 64

        y = TITLE_H + PAD
        self._rects["card_server"] = (PAD, y, content_w, info_h)
        y += info_h + GAP
        self._rects["card_status"] = (PAD, y, content_w, status_h)
        y += status_h + GAP
        self._rects["card_note"] = (PAD, y, content_w, note_h)

        bar_y = h - BAR_H
        self._rects["btn_close"] = (w - 44, 0, 44, TITLE_H)
        self._rects["chk_enable"] = (PAD + 2, bar_y + 16, 18, 18)
        self._rects["btn_enable"] = (PAD + 26, bar_y + 12, 180, 26)
        self._rects["btn_sync"] = (w - PAD - 96 - 12 - 110, bar_y + 12, 110, 28)
        self._rects["btn_save"] = (w - PAD - 96, bar_y + 12, 96, 28)

        # ---- 服务器卡内的字段网格
        fx = PAD + CARD_PAD
        fw = content_w - CARD_PAD * 2
        fy = TITLE_H + PAD + CARD_PAD + HEAD_H + 8

        self._rects["lbl_url"] = (fx, fy, 60, LBL_H)
        self._rects["f_url"] = (fx, fy + 15, fw - 110, FIELD_H)
        self._rects["btn_test"] = (fx + fw - 100, fy + 15, 100, FIELD_H)

        y2 = fy + ROW_STEP
        self._rects["lbl_user"] = (fx, y2, 120, LBL_H)
        self._rects["f_user"] = (fx, y2 + 15, 240, FIELD_H)
        self._rects["lbl_pass"] = (fx + 256, y2, 120, LBL_H)
        self._rects["f_pass"] = (fx + 256, y2 + 15, fw - 256 - 64, FIELD_H)
        self._rects["btn_show"] = (fx + fw - 56, y2 + 17, 56, 24)

        y3 = fy + ROW_STEP * 2
        self._rects["lbl_dir"] = (fx, y3, 120, LBL_H)
        self._rects["f_dir"] = (fx, y3 + 15, 200, FIELD_H)
        self._rects["lbl_interval"] = (fx + 216, y3, 120, LBL_H)
        self._rects["f_interval"] = (fx + 216, y3 + 15, 70, FIELD_H)
        self._rects["lbl_min"] = (fx + 292, y3 + 15, 60, FIELD_H)

        self._rects["f_note"] = (PAD + CARD_PAD, 0, 0, 0)

    def _create_edits(self):
        e = self.edits
        e["url"] = self.create_edit(0, 0, 10, 10, font=self.f_mono)
        e["user"] = self.create_edit(0, 0, 10, 10, font=self.f_value)
        e["pass"] = self.create_edit(0, 0, 10, 10, password=True, font=self.f_value)
        e["dir"] = self.create_edit(0, 0, 10, 10, font=self.f_mono)
        e["interval"] = self.create_edit(0, 0, 10, 10, font=self.f_mono)
        for name, font in (("url", self.f_mono), ("user", self.f_value),
                           ("pass", self.f_value), ("dir", self.f_mono),
                           ("interval", self.f_mono)):
            th, el = font.metrics(self.scale)
            self._edit_h[name] = max(EDIT_H_MIN, int(round((th + el) / self.scale)))
        self._apply_edits()

    def _apply_edits(self):
        sc = self.scale
        for name, key in (("url", "f_url"), ("user", "f_user"),
                          ("pass", "f_pass"), ("dir", "f_dir"),
                          ("interval", "f_interval")):
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

    def on_resize(self):
        self._relayout()
        self._apply_edits()

    # ------------------------------------------------------------------ 数据
    def reload(self):
        self.cfg = syncmod.load_config()
        self._enabled = bool(self.cfg.enabled)
        e = self.edits
        if "url" not in e:
            return
        e["url"].set_text(self.cfg.url)
        e["user"].set_text(self.cfg.username)
        e["pass"].set_text(self.cfg.password)
        e["dir"].set_text(self.cfg.remote_dir or "TokenBoard")
        e["interval"].set_text(str(self.cfg.interval_min or 30))
        self.invalidate()

    def _form_to_cfg(self) -> SyncConfig:
        cfg = self.cfg
        cfg.url = self.edits["url"].get_text().strip()
        cfg.username = self.edits["user"].get_text().strip()
        cfg.set_password(self.edits["pass"].get_text())
        cfg.remote_dir = self.edits["dir"].get_text().strip() or "TokenBoard"
        try:
            cfg.interval_min = max(1, min(1440, int(self.edits["interval"].get_text() or 30)))
        except ValueError:
            cfg.interval_min = 30
        cfg.enabled = bool(self._enabled)
        return cfg

    def _set_status(self, text: str, kind: str = "info"):
        self.status = text
        self.status_kind = kind
        self.invalidate()

    def _notify_changed(self):
        if self.on_changed:
            try:
                self.on_changed()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ 绘制
    def draw(self, c):
        c.fill(BASE)
        self._draw_title(c)
        self._draw_server(c)
        self._draw_status_card(c)
        self._draw_note(c)
        self._draw_bar(c)

    @staticmethod
    def _card(c, x, y, w, h, r=12):
        c.round_rect(x, y + 1.5, w, h, r, fill=SHADOW)
        c.round_rect(x, y, w, h, r, fill=SURFACE, stroke=CARD_LINE, stroke_w=1.0)
        c.line(x + r, y + 1, x + w - r, y + 1, CARD_TOP, 1)

    def _section(self, c, x, y, w, title, right=""):
        c.round_rect(x, y + 2, 2.5, 11, 1.2, fill=ACCENT)
        c.text(x + 9, y, 240, 16, title, self.f_head, TEXT_2,
               align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        if right:
            c.text(x, y, w, 16, right, self.f_tiny, TEXT_3,
                   align=DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

    def _well(self, c, r):
        if not r:
            return
        x, y, w, h = r
        c.round_rect(x, y, w, h, 6, fill=SURFACE_2, stroke=LINE_2, stroke_w=1)

    def _draw_title(self, c):
        ix, iy, isz = PAD, (TITLE_H - 20) / 2, 20
        c.round_rect(ix, iy, isz, isz, 6, fill=mix(SURFACE_2, ACCENT, 0.16),
                     stroke=mix(SURFACE_2, ACCENT, 0.32), stroke_w=1.0)
        # 云 + 上传箭头，和主面板的三根柱区分开
        c.line(ix + 5, iy + 12, ix + 15, iy + 12, "#A9B8D2", 1.4)
        c.line(ix + 7, iy + 8, ix + 13, iy + 8, "#A9B8D2", 1.4)
        c.polyline([(ix + 10, iy + 5), (ix + 7, iy + 8), (ix + 13, iy + 8)],
                   ACCENT, 1.6)

        c.text(ix + isz + 8, 0, 240, TITLE_H, "云同步 · WebDAV", self.f_title,
               TEXT, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        tw, _ = c.measure("云同步 · WebDAV", self.f_title)
        sep = ix + isz + 8 + max(90, tw + 14)
        c.line(sep, TITLE_H / 2 - 5, sep, TITLE_H / 2 + 5, LINE_2, 1)
        c.text(sep + 12, 0, 420, TITLE_H,
               "多台机器合并同一份用量，只用你自己的 WebDAV",
               self.f_tiny, TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

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

    def _draw_server(self, c):
        x, y, w, h = self._rects["card_server"]
        self._card(c, x, y, w, h)
        self._section(c, x + CARD_PAD, y + CARD_PAD, w - CARD_PAD * 2, "服务器")
        for key in ("f_url", "f_user", "f_pass", "f_dir", "f_interval"):
            self._well(c, self._rects.get(key))
        for key, label in (("lbl_url", "地址"), ("lbl_user", "用户名"),
                           ("lbl_pass", "密码"), ("lbl_dir", "远程目录"),
                           ("lbl_interval", "同步间隔")):
            r = self._rects.get(key)
            if r:
                c.text(r[0], r[1], r[2], r[3], label, self.f_label, TEXT_3,
                       align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        r = self._rects.get("lbl_min")
        if r:
            c.text(r[0], r[1], r[2], r[3], "分钟", self.f_label, TEXT_3,
                   align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)
        self._button(c, "btn_test", "测试连接")
        self._button(c, "btn_show", "隐藏" if self._show_key else "显示")

    def _draw_status_card(self, c):
        x, y, w, h = self._rects["card_status"]
        self._card(c, x, y, w, h)
        self._section(c, x + CARD_PAD, y + CARD_PAD, w - CARD_PAD * 2, "状态")

        ok = bool(self._enabled)
        dot = OK if ok else LINE_2
        c.ellipse(x + CARD_PAD + 1, y + 50, 8, 8, mix(SURFACE, dot, 0.30))
        c.ellipse(x + CARD_PAD + 2, y + 51, 6, 6, dot)

        left = ("已启用 · 每 %d 分钟自动同步" % self.cfg.interval_min) if ok else "未启用"
        c.text(x + CARD_PAD + 16, y + 42, 360, 20, left, self.f_value,
               TEXT if ok else TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

        right = ""
        if self.cfg.last_sync_at:
            right = f"上次同步 {_fmt_ts(self.cfg.last_sync_at)}（{_ago(self.cfg.last_sync_at)}）"
        elif self.cfg.last_status == "error":
            right = "还没成功同步过"
        if right:
            c.text(x + w - CARD_PAD - 340, y + 42, 340, 20, right, self.f_tiny,
                   TEXT_3, align=DT_RIGHT | DT_VCENTER | DT_SINGLELINE)

        try:
            lu, ls = self.store.counts()
        except Exception:  # noqa: BLE001
            lu = ls = 0
        line2 = (f"本地 {lu:,} 条用量 · {ls:,} 条速度采样"
                 f"　|　远端 {self.cfg.last_remote_count:,} 条 / "
                 f"{_fmt_size(self.cfg.last_remote_bytes)}")
        c.text(x + CARD_PAD, y + 66, w - CARD_PAD * 2, 18, line2, self.f_mono,
               TEXT_2, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

        err = self.cfg.last_error if self.cfg.last_status == "error" else ""
        msg = self.status or err
        kind = self.status_kind if self.status else ("err" if err else "info")
        color = {"ok": OK, "warn": WARN, "err": DANGER}.get(kind, TEXT_3)
        if self.busy:
            msg = f"正在{self.busy}…"
            color = TEXT_2
        if msg:
            c.text(x + CARD_PAD, y + 92, w - CARD_PAD * 2, 18, msg, self.f_tiny,
                   color, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

    def _draw_note(self, c):
        x, y, w, h = self._rects["card_note"]
        self._card(c, x, y, w, h)
        lines = [
            "只同步用量与速度采样，不含任何 API Key；密码经 Windows DPAPI 加密后只存在本机。",
            "两边按请求 id / 采样 id 合并，重复同步不会把数字刷大。",
        ]
        for i, text in enumerate(lines):
            c.text(x + CARD_PAD, y + 12 + i * 20, w - CARD_PAD * 2, 18, text,
                   self.f_tiny, TEXT_3, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

    def _draw_bar(self, c):
        bar_y = self.height - BAR_H
        c.line(PAD, bar_y - 8, self.width - PAD, bar_y - 8, LINE)

        r = self._rects["chk_enable"]
        on = bool(self._enabled)
        hot = self._hover in ("chk_enable", "btn_enable")
        c.round_rect(r[0], r[1], r[2], r[3], 4,
                     fill=mix(SURFACE, ACCENT, 0.85) if on else SURFACE_2,
                     stroke=mix(SURFACE_2, ACCENT, 0.6) if on else LINE_2,
                     stroke_w=1.0)
        if on:
            c.line(r[0] + 4, r[1] + 9, r[0] + 7.5, r[1] + 12.5, "#0C1220", 2)
            c.line(r[0] + 7.5, r[1] + 12.5, r[0] + 13.5, r[1] + 5.5, "#0C1220", 2)
        c.text(r[0] + r[2] + 8, bar_y + 12, 200, 26, "启用云同步", self.f_value,
               TEXT if hot else TEXT_2, align=DT_LEFT | DT_VCENTER | DT_SINGLELINE)

        self._button(c, "btn_sync", "立即同步", primary=False)
        self._button(c, "btn_save", "保存并关闭", primary=True)

    def _button(self, c, key, text, primary=False):
        r = self._rects.get(key)
        if not r:
            return
        x, y, w, h = r
        hot = self._hover == key
        if primary:
            fill = mix(ACCENT, "#FFFFFF", 0.18) if hot else ACCENT
            fg = "#0C1220"
            stroke = None
        else:
            fill = SURFACE_3 if hot else SURFACE_2
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
        for key in ("btn_close", "btn_test", "btn_show", "btn_sync",
                    "btn_save", "chk_enable", "btn_enable"):
            if self._in(key, x, y):
                hot = key
                break
        if hot != self._hover:
            self._hover = hot
            self.invalidate()

    def on_click(self, x: float, y: float):
        if self._in("btn_close", x, y):
            self.on_close()
            return
        if self._in("btn_show", x, y):
            self._show_key = not self._show_key
            self.edits["pass"].set_password_char("" if self._show_key else "\u2022")
            self.invalidate()
            return
        if self._in("chk_enable", x, y) or self._in("btn_enable", x, y):
            self._enabled = not self._enabled
            self.invalidate()
            return
        if self._in("btn_test", x, y):
            self._test()
            return
        if self._in("btn_sync", x, y):
            self._sync_now()
            return
        if self._in("btn_save", x, y):
            self._save(close=True)
            return
        # 点空白处：让输入框失焦，别一直闪光标
        try:
            self.focus()
        except Exception:  # noqa: BLE001
            pass

    def on_nc_hit_test(self, x: float, y: float) -> int:
        if 0 <= y < TITLE_H:
            if self._in("btn_close", x, y):
                return HTCLIENT
            return HTCAPTION
        return super().on_nc_hit_test(x, y)

    def on_key(self, key: int):
        if key == 0x1B:            # ESC
            self.on_close()
        elif key == 0x0D:          # Enter
            self._save(close=True)

    # ------------------------------------------------------------------ 动作
    def _save(self, close: bool = False):
        cfg = self._form_to_cfg()
        if cfg.enabled and not cfg.url.strip():
            self._set_status("启用前先填服务器地址", "warn")
            return
        if cfg.enabled and not cfg.url.lower().startswith(("http://", "https://")):
            self._set_status("地址要以 http:// 或 https:// 开头", "warn")
            return
        try:
            syncmod.save_config(cfg)
        except OSError as e:
            self._set_status(f"保存失败：{e}", "err")
            return
        self.cfg = syncmod.load_config()
        self._set_status("已保存", "ok")
        self._notify_changed()
        if close:
            self.on_close()

    def _test(self):
        cfg = self._form_to_cfg()
        if not cfg.url.strip():
            self._set_status("先填服务器地址", "warn")
            return

        def job():
            return ("probe", syncmod.probe(cfg))

        self._run_bg("测试连接", job)

    def _sync_now(self):
        cfg = self._form_to_cfg()
        if not cfg.url.strip():
            self._set_status("先填服务器地址", "warn")
            return
        # 立即同步用的是「表单里的配置」，所以先落盘再同步
        syncmod.save_config(cfg)

        def job():
            return ("sync", syncmod.sync_once(self.store, cfg, force=True))

        self._run_bg("同步", job)

    def _run_bg(self, label: str, fn):
        if self.busy:
            self._set_status(f"「{self.busy}」还没结束，稍等", "warn")
            return
        self.busy = label
        self._bg_result = None      # 必须在起线程之前清空（见 configwin 里的注释）

        def work():
            try:
                result = fn()
            except Exception as e:  # noqa: BLE001
                result = ("error", f"{type(e).__name__}: {e}")
            with self._busy_lock:
                self._bg_result = result
                self.busy = ""

        threading.Thread(target=work, daemon=True).start()
        self.invalidate()

    def on_timer(self, tid: int):
        with self._busy_lock:
            result = self._bg_result
            if result is not None:
                self._bg_result = None
        if result is None:
            return
        kind, payload = result
        if kind == "error":
            self._set_status(f"失败：{payload}", "err")
        elif kind == "probe":
            self._set_status(("✓ " if payload["ok"] else "✗ ") + payload["message"],
                             "ok" if payload["ok"] else "err")
        elif kind == "sync":
            res = payload
            self._set_status(("✓ " if res.ok else "✗ ") + res.summary(),
                             "ok" if res.ok else "err")
        self.cfg = syncmod.load_config()
        self._notify_changed()
        self.invalidate()