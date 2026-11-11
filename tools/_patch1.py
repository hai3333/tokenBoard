import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

old_init = "        self._dot_hit: list[tuple[str, float, float, float]] = []\n        self.tray = None"
new_init = (
    "        self._dot_hit: list[tuple[str, float, float, float]] = []\n"
    "        self._ctx_row = -1          # 右键菜单目标行\n"
    "        self._ctx_x = 0.0\n"
    "        self._ctx_y = 0.0\n"
    "        self._ctx_items: list[tuple[str, str]] = []   # [(id, label), ...]\n"
    "        self._ctx_hot = -1          # 菜单项悬停索引\n"
    "        self._search_q = \"\"         # 搜索关键字\n"
    "        self._search_focus = False\n"
    "        self.tray = None"
)
assert old_init in src, "init not found"
src = src.replace(old_init, new_init, 1)
p.write_text(src, encoding="utf-8")
print("init ok")
