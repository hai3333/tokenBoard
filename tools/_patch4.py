import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# 1) on_click 中：右键菜单点击处理 + 行右键打开菜单
old_seg = """        i = self._row_at(x, y)
        if i >= 0:
            key = self._rows[i]["key"]
            if key in self._expanded:
                self._expanded.discard(key)
            else:
                self._expanded.add(key)
            self.invalidate()
            return"""
new_seg = """        # 右键菜单：点击菜单项
        if self._ctx_items:
            hit = self._ctx_hit_item(x, y)
            if hit >= 0:
                self._exec_ctx(hit)
                return
            self._ctx_items = []
            self.invalidate()
            return
        i = self._row_at(x, y)
        if i >= 0:
            key = self._rows[i]["key"]
            if key in self._expanded:
                self._expanded.discard(key)
            else:
                self._expanded.add(key)
            self.invalidate()
            return"""
assert old_seg in src
src = src.replace(old_seg, new_seg, 1)
p.write_text(src, encoding="utf-8")
print("ctx click ok")
