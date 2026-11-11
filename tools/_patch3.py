import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# 在 _tb_button_at 前插入搜索框相关方法
anchor = "    # ---- 通用卡片 ------------------------------------------------------"
assert anchor in src, "anchor not found"

helpers = '''    # ---- 搜索框 ----------------------------------------------------------
    def _search_rect(self) -> tuple[float, float, float, float]:
        """搜索框在标题栏右侧，齿轮按钮左边。"""
        w = 170.0
        h = 20.0
        x = TB_GEAR_X - w - 12
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
        # 放大镜图标
        cx, cy = x + 12, y + h / 2
        c.ellipse(cx - 4, cy - 4, 8, 8, stroke=TEXT_3, stroke_w=1.2)
        c.line(cx + 3, cy + 3, cx + 6, cy + 6, TEXT_3, 1.2)
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
            items.append(("sep", ""))
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
                data = (text + "\\0").encode("utf-16-le")
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

'''

src = src.replace(anchor, helpers + anchor, 1)
p.write_text(src, encoding="utf-8")
print("helpers ok")
