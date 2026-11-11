    # ==================================================================
    # 绘制
    # ==================================================================
    def draw(self, c: Canvas):
        c.fill(BASE)
        self._load()
        self._draw_header(c)
        if self._view_idx == 2:
            self._draw_quota(c)
        else:
            self._draw_hero(c)
            self._draw_table(c)
        self._draw_footer(c)

    # ---- 顶部控件条 --------------------------------------------------
    def _draw_header(self, c: Canvas):
        self._draw_seg(c, VIEW_SEG_X, SEG_Y, VIEW_SEG_W,
                       [v[0] for v in VIEWS], self._view_idx)
        if self._view_idx == 2:
            # 额度是实时的，时间范围对它没意义 —— 换成刷新说明
            c.text(WIN_W - PAD - 240, SEG_Y + 4, 240, 16,
                   "额度每 5 分钟自动刷新", self.f_small, TEXT_3,
                   align=DT_R | DT_VC | DT_SL)
        else:
            self._draw_seg(c, PERIOD_SEG_X, SEG_Y, PERIOD_SEG_W,
                           [p[0] for p in PERIODS], self._period_idx)
        c.line(0, HEAD_H, WIN_W, HEAD_H, LINE)

    def _draw_seg(self, c: Canvas, x, y, w, items, sel):
        n = len(items)
        c.round_rect(x - 3, y - 3, w * n + 6, SEG_H + 6, (SEG_H + 6) / 2,
                     fill=SURFACE_2)
        for i, name in enumerate(items):
            ix = x + i * w
            if i == sel:
                c.round_rect(ix, y, w, SEG_H, SEG_H / 2, fill=SURFACE_3)
                c.text(ix, y, w, SEG_H, name, self.f_seg_sel, TEXT,
                       align=DT_C | DT_VC | DT_SL)
            else:
                c.text(ix, y, w, SEG_H, name, self.f_seg, TEXT_2,
                       align=DT_C | DT_VC | DT_SL)

    # ---- 左侧概览卡 --------------------------------------------------
    def _draw_hero(self, c: Canvas):
        x, y, w = HERO_X, BODY_Y, HERO_W
        c.round_rect(x, y, w, BODY_H, 12, fill=SURFACE)
        px = x + 16
        pw = w - 32

        # 品牌标记：三根递增的柱，就是消耗曲线本身
        by = y + 20
        for i, (bh, col) in enumerate([(6, "#39445C"), (10, "#6E86B8"),
                                       (14, ACCENT)]):
            c.round_rect(px + i * 6, by + (14 - bh), 4, bh, 2, fill=col)
        c.text(px + 24, y + 13, 140, 18, "TokenBoard", self.f_title, TEXT,
               align=DT_L | DT_VC | DT_SL)
        c.text(px, y + 38, pw, 14, "本机 AI IDE Token 消耗", self.f_sub, TEXT_3,
               align=DT_L | DT_VC | DT_SL)

        t = self._totals
        # 总量是这一屏里唯一的「主数字」
        c.text(px, y + 56, pw, 42, fmt_tokens(t["total"]), self.f_big, TEXT,
               align=DT_L | DT_VC | DT_SL)
        c.text(px, y + 96, pw, 13, "tokens", self.f_unit, TEXT_3,
               align=DT_L | DT_VC | DT_SL)
        c.text(px, y + 114, pw, 15,
               f"{PERIODS[self._period_idx][0]} · {t['reqs']:,} 次请求",
               self.f_meta, TEXT_2, align=DT_L | DT_VC | DT_SL)

        c.line(px, y + 138, px + pw, y + 138, LINE)

        iy = y + 150
        for name, val in (("输入", t["input"]), ("输出", t["output"]),
                          ("缓存读", t["cache"])):
            c.text(px, iy, 60, 16, name, self.f_meta, TEXT_3,
                   align=DT_L | DT_VC | DT_SL)
            c.text(px + pw - 90, iy - 1, 90, 16, fmt_tokens(val), self.f_num,
                   TEXT, align=DT_R | DT_VC | DT_SL)
            iy += 22

        c.line(px, y + 220, px + pw, y + 220, LINE)

        # 趋势图
        peak = max(self._spark) if self._spark else 0
        c.text(px, y + 230, pw - 70, 13, "近 30 天消耗趋势", self.f_meta, TEXT_3,
               align=DT_L | DT_VC | DT_SL)
        if peak:
            c.text(px + pw - 80, y + 230, 80, 13, f"峰值 {fmt_tokens(peak)}",
                   self.f_tinyb, TEXT_3, align=DT_R | DT_VC | DT_SL)
        self._draw_spark(c, px, y + 248, pw, 44)

    def _draw_spark(self, c: Canvas, x, y, w, h):
        vals = self._spark
        if not vals or max(vals) <= 0:
            c.text(x, y + h / 2 - 8, w, 16, "暂无数据", self.f_small, TEXT_3,
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
            t = row / span
            c.fill_rect(min(xs), yb, max(1.0, max(xs) - min(xs)), 1,
                        mix(SURFACE, ACCENT, 0.34 * (1 - t) ** 1.5))
        c.polyline(pts, ACCENT, 1.8)
        # 今天：实心点
        c.ellipse(pts[-1][0] - 3, pts[-1][1] - 3, 6, 6, ACCENT)

    # ---- 右侧列表 ----------------------------------------------------
    def _row_height(self, row: dict) -> int:
        return ROW_SUB if row["kind"] == "sub" else (
            ROW_APP if row["kind"] == "app" else ROW_MODEL)

    def _layout_rows(self) -> None:
        """算好每行的 y 坐标（不依赖是否已经画过）。"""
        self._row_y = []
        y = BODY_Y
        for r in self._rows:
            self._row_y.append(y)
            y += self._row_height(r)
        self._content_h = y - BODY_Y

    def _visible_count(self) -> int:
        """一屏能显示多少行。"""
        used = 0
        n = 0
        for r in self._rows:
            h = self._row_height(r)
            if used + h > BODY_H:
                break
            used += h
            n += 1
        return max(1, n)

    def _draw_table(self, c: Canvas):
        rows = self._rows
        if not rows:
            c.text(LIST_X, BODY_Y + 20, 300, 20, "没有数据", self.f_small, TEXT_3,
                   align=DT_L | DT_VC | DT_SL)
            return

        max_scroll = max(0, len(rows) - self._visible_count())
        self._scroll = max(0, min(self._scroll, max_scroll))
        base = self._row_y[self._scroll]

        bottom = BODY_Y + BODY_H
        drawn = 0
        for i in range(self._scroll, len(rows)):
            row = rows[i]
            y = BODY_Y + (self._row_y[i] - base)
            h = self._row_height(row)
            if y + h > bottom:
                break
            self._draw_row(c, row, y, h)
            drawn += 1

        if len(rows) > drawn:
            track_h = BODY_H
            frac = max(0.12, drawn / len(rows))
            thumb_h = max(20, int(track_h * frac))
            pos = int((track_h - thumb_h) *
                      (self._scroll / max(1, len(rows) - drawn)))
            c.round_rect(VAL_X + VAL_W + 4, BODY_Y, 3, track_h, 2, fill=SURFACE_2)
            c.round_rect(VAL_X + VAL_W + 4, BODY_Y + pos, 3, thumb_h, 2, fill=LINE_2)

    def _draw_row(self, c: Canvas, row: dict, y: int, h: int) -> None:
        kind = row["kind"]
        mx = row.get("max") or 1
        has = row.get("has", True)
        color = row["color"] if has else LINE_2

        if kind == "sub":
            # 子行：缩进 + 小圆点 + 细条
            c.ellipse(SUB_DOT_X, y + 10, 5, 5, color)
            c.text(SUB_NAME_X, y + 5, SUB_NAME_W, 16, row["name"],
                   self.f_subname, TEXT_2, align=DT_L | DT_VC | DT_SL)
            c.round_rect(SUB_BAR_X, y + 11, SUB_BAR_W, 4, 2, fill=SURFACE_2)
            c.round_rect(SUB_BAR_X, y + 11,
                        max(2, int(SUB_BAR_W * row["tokens"] / mx)), 4, 2, fill=color)
            c.text(VAL_X + 26, y + 5, VAL_W - 26, 16, fmt_tokens(row["tokens"]),
                   self.f_subval, TEXT, align=DT_R | DT_VC | DT_SL)
            c.text(VAL_X + VAL_W - 34, y + 6, 34, 16, f"{row['pct']:.0f}%",
                   self.f_subname, TEXT_3, align=DT_R | DT_VC | DT_SL)
            return

        # 主行
        if self._hover_row == self._row_index_of(y):
            c.round_rect(LIST_X - 8, y + 1, LIST_W + 12, h - 2, 8, fill=SURFACE_2)

        if kind == "app":
            name_x, name_w = NAME_X, NAME_W
            bar_x, bar_w = BAR_X, BAR_W
        else:
            name_x, name_w = M_NAME_X, M_NAME_W
            bar_x, bar_w = M_BAR_X, M_BAR_W

        # 品牌色竖条
        c.round_rect(TICK_X, y + 9, TICK_W, 16, 1.5, fill=color)
        # 展开箭头
        c.text(TICK_X + 9, y + 6, 12, 16,
               DISCLOSURE_OPEN if row["open"] else DISCLOSURE_CLOSED,
               self.f_tiny, TEXT_3, align=DT_L | DT_VC | DT_SL)
        # 名称
        c.text(name_x, y + 6, name_w, 18, row["name"], self.f_name,
               TEXT if has else TEXT_3, align=DT_L | DT_VC | DT_SL)
        # 进度条
        c.round_rect(bar_x, y + 10, bar_w, 5, 2.5, fill=SURFACE_2)
        if has:
            c.round_rect(bar_x, y + 10, max(3, int(bar_w * row["tokens"] / mx)),
                        5, 2.5, fill=color)
        # 数值
        c.text(VAL_X, y + 6, VAL_W, 18, fmt_tokens(row["tokens"]), self.f_val,
               TEXT if has else TEXT_3, align=DT_R | DT_VC | DT_SL)
        # 第二行：主力模型 / 主要来源
        if kind == "app" and row.get("sub"):
            c.text(name_x, y + 26, name_w + 60, 14,
                   f"主力 {row['sub']}", self.f_tiny, TEXT_3,
                   align=DT_L | DT_VC | DT_SL)

    def _row_index_of(self, y: int) -> int:
        for i, ry in enumerate(self._row_y):
            if ry == y:
                return i
        return -1

    # ---- 订阅额度 ----------------------------------------------------
    def _quota_blocks(self) -> list[tuple[dict, float]]:
        """返回 [(额度项, 卡片高度)]，高度随限额条数变化。"""
        out = []
        for q in (self._quota or []):
            wins = q.get("windows") or []
            out.append((q, 58 if not wins else 26 + len(wins) * 40 + 12))
        return out

    def _draw_quota(self, c: Canvas):
        blocks = self._quota_blocks()
        if not blocks:
            c.round_rect(PAD, BODY_Y, QUOTA_W, 64, 12, fill=SURFACE)
            c.text(PAD + 18, BODY_Y + 22, QUOTA_W - 36, 20, "正在获取订阅额度…",
                   self.f_meta, TEXT_3, align=DT_L | DT_VC | DT_SL)
            return

        gap = QUOTA_GAP
        total = sum(h for _, h in blocks) + gap * (len(blocks) - 1)
        max_scroll = max(0.0, total - BODY_H)
        self._quota_scroll = max(0.0, min(self._quota_scroll, max_scroll))

        token = c.push_clip(PAD, BODY_Y, QUOTA_W, BODY_H)
        y = BODY_Y - self._quota_scroll
        for q, h in blocks:
            self._draw_quota_card(c, q, y, h, QUOTA_W)
            y += h + gap
        c.pop_clip(token)

        if total > BODY_H:
            frac = max(0.12, BODY_H / total)
            thumb_h = max(20, int(BODY_H * frac))
            pos = int((BODY_H - thumb_h) * (self._quota_scroll /
                                           max(1.0, total - BODY_H)))
            c.round_rect(VAL_X + VAL_W + 4, BODY_Y, 3, BODY_H, 2, fill=SURFACE_2)
            c.round_rect(VAL_X + VAL_W + 4, BODY_Y + pos, 3, thumb_h, 2, fill=LINE_2)

    def _draw_quota_card(self, c: Canvas, q: dict, y: float, h: float,
                         w: float):
        c.round_rect(PAD, y, w, h, 12, fill=SURFACE)
        color = QUOTA_COLOR.get(q.get("provider", ""), ACCENT)

        ok = q.get("ok")
        dot = OK if ok else (DANGER if q.get("error") else LINE_2)
        c.ellipse(PAD + 16, y + 13, 7, 7, dot)
        c.text(PAD + 30, y + 8, 300, 18, q.get("name", ""), self.f_name, TEXT,
               align=DT_L | DT_VC | DT_SL)

        right = q.get("note") or ""
        if not right and q.get("windows"):
            right = f"{len(q['windows'])} 项限额"
        if right:
            c.text(PAD + w - 260, y + 9, 244, 16, right, self.f_small, TEXT_3,
                   align=DT_R | DT_VC | DT_SL)

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
        c.line(PAD, FOOT_Y - 10, WIN_W - PAD, FOOT_Y - 10, LINE)
        x = PAD
        yy = FOOT_Y
        self._dot_hit = []
        for app in APP_META:
            state = self._status.get(app)
            ok = state[0] if state else None
            dot = OK if ok else (DANGER if ok is False else LINE_2)
            c.ellipse(x, yy + 3, 7, 7, dot)
            label = APP_META[app].get("short", app_label(app))
            tw, _ = c.measure(label, self.f_small)
            c.text(x + 12, yy, tw + 4, 16, label, self.f_small,
                   TEXT_2 if ok else (DANGER if ok is False else TEXT_3),
                   align=DT_L | DT_VC | DT_SL)
            self._dot_hit.append((app, x, yy, 12 + tw + 4))
            x += 12 + tw + 14

        c.text(VAL_X + VAL_W - 200, yy, 200, 16, self._footer_msg(),
               self.f_small, TEXT_3, align=DT_R | DT_VC | DT_SL)

    def _footer_msg(self) -> str:
        if self._status_error:
            return self._status_error
        return f"更新于 {self._last_update}"
