import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\win32.py")
src = p.read_text(encoding="utf-8")

old = """        if msg == WM_LBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._mouse_x = x / self.scale
            self._mouse_y = y / self.scale
            self.on_click_up(self._mouse_x, self._mouse_y)
            return 0"""
new = """        if msg == WM_LBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._mouse_x = x / self.scale
            self._mouse_y = y / self.scale
            self.on_click_up(self._mouse_x, self._mouse_y)
            return 0
        if msg == WM_RBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._mouse_x = x / self.scale
            self._mouse_y = y / self.scale
            self.on_right_click(self._mouse_x, self._mouse_y)
            return 0
        if msg == WM_CHAR:
            # 仅转发给窗口用于搜索输入；未聚焦时什么也不发生
            if self.on_char(chr(wparam)):
                return 0"""
assert old in src
src = src.replace(old, new, 1)

old_hook = """    def on_click(self, x: float, y: float):"""
new_hook = """    def on_right_click(self, x: float, y: float):
        \"\"\"默认忽略。子类覆盖打开右键菜单。\"\"\"

    def on_char(self, ch: str) -> bool:
        \"\"\"返回 True 表示字符已被消费（搜索框）。默认不消费。\"\"\"
        return False

    def on_click(self, x: float, y: float):"""
assert old_hook in src
src = src.replace(old_hook, new_hook, 1)
p.write_text(src, encoding="utf-8")
print("win32 ok")
