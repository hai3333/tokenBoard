import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# --- 1) _load: 过滤后再布局 ---
anchor = """        self._layout_rows()
        if self._view_idx != 3:
            self._spark = self._load_spark()"""
repl = """        self._apply_search_filter()
        self._layout_rows()
        if self._view_idx != 3:
            self._spark = self._load_spark()"""
assert anchor in src
src = src.replace(anchor, repl, 1)

# --- _apply_search_filter 方法（挂在 _load_spark 之后） ---
anchor2 = "    def _load_spark(self) -> list[float]:"
method = '''    def _apply_search_filter(self) -> None:
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

'''
assert anchor2 in src
src = src.replace(anchor2, method + anchor2, 1)

# --- 2) draw(): 标题栏后画搜索框；最末尾画右键菜单 ---
old_draw = """        self._draw_titlebar(c)
        self._draw_header(c)"""
new_draw = """        self._draw_titlebar(c)
        self._draw_search(c)
        self._draw_header(c)"""
assert old_draw in src
src = src.replace(old_draw, new_draw, 1)

old_tail = """        self._draw_footer(c)"""
new_tail = """        self._draw_footer(c)
        self._draw_ctx_menu(c)"""
assert old_tail in src
src = src.replace(old_tail, new_tail, 1)

# --- 3) on_key: 搜索聚焦时吞掉按键；R 刷新 ---
old_key = """    def on_key(self, key: int) -> None:
        \"\"\"键盘：↑↓/PgUp/PgDn/Home/End 滚动，1-4 切视图。\"\"\"
        if 0x31 <= key <= 0x34:                    # '1'..'4'"""
new_key = """    def on_key(self, key: int) -> None:
        \"\"\"键盘：↑↓/PgUp/PgDn/Home/End 滚动，1-4 切视图；R 手动刷新。\"\"\"
        if self._search_focus:
            # 搜索输入中：Esc 退出，其余按键交给 on_char
            if key == 0x1B:
                self._search_focus = False
                self.invalidate()
            return
        if key == 0x52:                            # 'R' 手动扫描刷新
            self._start_scan()
            return
        if 0x31 <= key <= 0x34:                    # '1'..'4'"""
assert old_key in src
src = src.replace(old_key, new_key, 1)

# --- 4) on_char / on_right_click ---
anchor3 = "    def on_hover(self) -> None:"
hooks = '''    def on_char(self, ch: str) -> bool:
        """搜索框输入。返回 True 表示已消费。"""
        if not self._search_focus:
            return False
        if ch == "\\x08":                       # Backspace
            self._search_q = self._search_q[:-1]
        elif ch == "\\r" or ch == "\\n":        # Enter：收起键盘焦点，保留过滤词
            self._search_focus = False
        elif ch == "\\x1b":                     # Esc：清空并退出
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

'''
assert anchor3 in src
src = src.replace(anchor3, hooks + anchor3, 1)

# --- 5) 右键菜单：去掉 sep 项（少画一项少出错） ---
old_items = """            items.append(("filter", f"只看「{row.get('name', '')}」"))
            items.append(("sep", ""))
            items.append(("copy", "复制名称"))"""
new_items = """            items.append(("filter", f"只看「{row.get('name', '')}」"))
            items.append(("copy", "复制名称"))"""
assert old_items in src
src = src.replace(old_items, new_items, 1)

# `sep` 分支仍保留无碍（菜单里已没有）

# --- 6) on_click: 搜索聚焦时点搜索框以外的区域 → 退出输入态 ---
old_blur = """        if self._search_box_at(x, y):
            self._search_focus = not self._search_focus
            if not self._search_focus and self._search_q:
                self._search_q = ""
            self.invalidate()
            return"""
new_blur = """        if self._search_box_at(x, y):
            if self._search_focus:
                self._search_focus = False
            else:
                self._search_focus = True
            self.invalidate()
            return
        if self._search_focus:
            self._search_focus = False
            self.invalidate()"""
assert old_blur in src
src = src.replace(old_blur, new_blur, 1)

# --- 7) on_hover: 菜单打开时跟踪悬停项 ---
old_hover = """        mx, my = self._mouse_x, self._mouse_y
        new_tb = self._tb_button_at(mx, my)"""
new_hover = """        mx, my = self._mouse_x, self._mouse_y
        if self._ctx_items:
            hot = self._ctx_hit_item(mx, my)
            if hot != self._ctx_hot:
                self._ctx_hot = hot
                self.invalidate()
        new_tb = self._tb_button_at(mx, my)"""
assert old_hover in src
src = src.replace(old_hover, new_hover, 1)

# --- 8) 快捷键提示（页脚居中） ---
old_foot = """        # 右侧：更新时刻，前面加一个极小的状态灯（有错就变红）
        msg = self._footer_msg()"""
new_foot = """        # 中部：快捷键提示（小号暗字，不抢状态圆点）
        hint = "1-4 切视图 · 滚轮滚动 · R 刷新"
        hw, _ = c.measure(hint, self.f_tiny)
        c.text(WIN_W / 2 - hw / 2, yy + 1, hw, 16, hint, self.f_tiny, TEXT_3,
               align=DT_C | DT_VC | DT_SL)

        # 右侧：更新时刻，前面加一个极小的状态灯（有错就变红）
        msg = self._footer_msg()"""
assert old_foot in src
src = src.replace(old_foot, new_foot, 1)

# 中部提示可能与左侧圆点重叠时让位（左侧足够宽就不画）
assert "hint = " in src

p.write_text(src, encoding="utf-8")
print("patch7 ok")
