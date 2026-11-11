import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# 顶部：右键菜单最高优先级（任何点击先尝试落在菜单上 / 否则关菜单）
old = """    def on_click(self, x: float, y: float):
        # 标题栏按钮：按下时先记下，抬起时再确认（避免误触直接关窗）
        if y < TITLE_H:"""
new = """    def on_click(self, x: float, y: float):
        # 右键菜单打开时，点击必须先处理它（命中菜单项则执行，否则关闭）
        if self._ctx_items:
            hit = self._ctx_hit_item(x, y)
            if hit >= 0:
                self._exec_ctx(hit)
            else:
                self._ctx_items = []
                self.invalidate()
            return
        # 标题栏按钮：按下时先记下，抬起时再确认（避免误触直接关窗）
        if y < TITLE_H:"""
assert old in src
src = src.replace(old, new, 1)

# 删除旧的位置
old2 = """        if self._view_idx == 3:
            return
        # 右键菜单：点击菜单项
        if self._ctx_items:
            hit = self._ctx_hit_item(x, y)
            if hit >= 0:
                self._exec_ctx(hit)
                return
            self._ctx_items = []
            self.invalidate()
            return
        i = self._row_at(x, y)"""
new2 = """        # 额度视图没有表格，别去碰上一屏残留的行）
        if self._view_idx == 3:
            return
        i = self._row_at(x, y)"""
assert old2 in src
src = src.replace(old2, new2, 1)
p.write_text(src, encoding="utf-8")
print("ctx priority ok")
