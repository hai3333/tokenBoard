import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\mini.py")
src = p.read_text(encoding="utf-8")

# 1) 数据里记住今天 top3 工具
old = """        self._apps: list[str] = []
        self._hover = False"""
new = """        self._apps: list[str] = []
        self._top3: list[tuple[str, int]] = []   # 今天用量前三（图标 + Token 数）
        self._hover = False"""
assert old in src
src = src.replace(old, new, 1)

old2 = """            self._apps = [r["app"] for r in rows
                          if (r["total_tokens"] or 0) > 0]
            if not self._apps:
                self._apps = list(APP_META.keys())"""
new2 = """            self._apps = [r["app"] for r in rows
                          if (r["total_tokens"] or 0) > 0]
            if not self._apps:
                self._apps = list(APP_META.keys())
            self._top3 = sorted(
                ((r["app"], int(r["total_tokens"] or 0)) for r in rows),
                key=lambda t: -t[1])[:3]"""
assert old2 in src
src = src.replace(old2, new2, 1)

# 2) 悬停时“今天 · N 次”这一行换成 top3 速览
old3 = """        # 今天 · N 次请求 · 成本（小框也把成本带上，不然还得点开大面板）
        money = fmt_mini_money(self._cost)
        c.text(PAD, 24, MINI_W - PAD * 2 - 14, 14,
               f"今天 · {self._reqs:,} 次 · {money}", self.f_meta, TEXT_3,
               align=DT_L | DT_VC | DT_SL)"""
new3 = """        # 今天 · N 次请求 · 成本；悬停时换成今天 top3 工具速览
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
                   align=DT_L | DT_VC | DT_SL)"""
assert old3 in src
src = src.replace(old3, new3, 1)

# 3) f_tiny 字体（悬停行用小一号，塞三个图标 + 数字）
old4 = """        self.f_brand = Font(10, 700)
        self.f_num = Font(20, 700, "Consolas")
        self.f_meta = Font(9, 400)"""
new4 = """        self.f_brand = Font(10, 700)
        self.f_num = Font(20, 700, "Consolas")
        self.f_meta = Font(9, 400)
        self.f_tiny = Font(8, 400, "Consolas")"""
assert old4 in src
src = src.replace(old4, new4, 1)

# 4) 需要 DT_L/DT_VC/DT_SL —— 已 import；APP_META 已 import ✅
p.write_text(src, encoding="utf-8")
print("mini top3 ok")
