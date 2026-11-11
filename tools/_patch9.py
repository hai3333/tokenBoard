import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# on_click：把搜索框判断移入 y<TITLE_H 分支内（搜索框就画在标题栏里）
old = """        # 标题栏按钮：按下时先记下，抬起时再确认（避免误触直接关窗）
        if y < TITLE_H:
            btn = self._tb_button_at(x, y)
            if btn:
                self._pressed_tb = btn
                self.invalidate()
            return
        # 搜索框：点击进入输入态，再点一次退出
        if self._search_box_at(x, y):
            if self._search_focus:
                self._search_focus = False
            else:
                self._search_focus = True
            self.invalidate()
            return
        if self._search_focus:
            self._search_focus = False
            self.invalidate()"""
new = """        # 标题栏：搜索框命中优先，其次窗口按钮
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
            self.invalidate()"""
assert old in src
src = src.replace(old, new, 1)
p.write_text(src, encoding="utf-8")
print("on_click reorder ok")
