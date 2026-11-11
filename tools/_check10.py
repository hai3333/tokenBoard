import pathlib
src = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py").read_text(encoding="utf-8")
actual_old2 = (
    "        if not rows:\n"
    '            hint = ("本期没有用量" if self._view_idx != 2\n'
    '                    else "本期还没有速度采样")'
)
wrong_old2 = (
    "        if not rows:\n"
    '            hint = ("本期没有用量" if self._view_idx != 2\n'
    '                    else "当前没有速度样本")'
)
print("actual old2 in src:", actual_old2 in src)
print("wrong  old2 in src:", wrong_old2 in src)
print("patched empty-hint marker 没有匹配:", "没有匹配" in src)
print("footer hint marker:", "1-4 切视图 · 滚轮 · R 刷新" in src)
print("hint_x:", "hint_x" in src)
