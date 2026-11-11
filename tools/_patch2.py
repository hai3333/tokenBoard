import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# 1) 扩大展开命中区：点整行任意处都能展开（原来只在行内）
old_row = """        i = self._row_at(x, y)
        if i >= 0:
            key = self._rows[i]["key"]
            if key in self._expanded:
                self._expanded.discard(key)
            else:
                self._expanded.add(key)
            self.invalidate()
            return"""
new_row = """        i = self._row_at(x, y)
        if i >= 0:
            key = self._rows[i]["key"]
            if key in self._expanded:
                self._expanded.discard(key)
            else:
                self._expanded.add(key)
            self.invalidate()
            return"""
assert old_row in src
# 2) 在 on_click 开头加搜索框命中
old_click = """    def on_click(self, x: float, y: float):
        # 标题栏按钮：按下时先记下，抬起时再确认（避免误触直接关窗）
        if y < TITLE_H:
            btn = self._tb_button_at(x, y)
            if btn:
                self._pressed_tb = btn
                self.invalidate()
            return"""
new_click = """    def on_click(self, x: float, y: float):
        # 标题栏按钮：按下时先记下，抬起时再确认（避免误触直接关窗）
        if y < TITLE_H:
            btn = self._tb_button_at(x, y)
            if btn:
                self._pressed_tb = btn
                self.invalidate()
            return
        # 搜索框：点击进入输入态，再点一次退出
        if self._search_box_at(x, y):
            self._search_focus = not self._search_focus
            if not self._search_focus and self._search_q:
                self._search_q = ""
            self.invalidate()
            return"""
assert old_click in src, "on_click not found"
src = src.replace(old_click, new_click, 1)
p.write_text(src, encoding="utf-8")
print("on_click ok")
