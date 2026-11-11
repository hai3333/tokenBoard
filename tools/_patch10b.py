import pathlib

p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# --- 1) 页脚提示：右对齐贴状态消息左侧；空间不够则不画 ---
lines = src.split("\n")
out = []
i = 0
replaced_footer = False
while i < len(lines):
    line = lines[i]
    if not replaced_footer and line.strip().startswith('hint = "1-4'):
        # 整个提示块：从注释行（上一行，已在 out 末尾）重发
        if out and "快捷键提示" in out[-1]:
            out.pop()  # 丢掉旧注释行
        indent = "        "
        out.append(indent + "# 快捷键提示（小号暗字）：贴状态消息左侧；空间不够不画")
        out.append(indent + 'hint = "1-4 切视图 · 滚轮 · R 刷新"')
        out.append(indent + "hw, _ = c.measure(hint, self.f_tiny)")
        out.append(indent + "hint_x = WIN_W - PAD - 220 - 10 - hw")
        out.append(indent + "if hint_x > x + 10:")
        out.append(indent + "    c.text(hint_x, yy + 1, hw, 16, hint, self.f_tiny, TEXT_3,")
        out.append(indent + "           align=DT_L | DT_VC | DT_SL)")
        # 跳过旧的 5 行提示块（measure/text/align 两行）
        i += 1
        while i < len(lines) and not lines[i].lstrip().startswith("# 右侧"):
            i += 1
        replaced_footer = True
        continue
    out.append(line)
    i += 1
src = "\n".join(out)
assert replaced_footer, "footer hint block not found"

# --- 2) 空列表提示：搜索无结果给专属文案 ---
old2 = (
    "        if not rows:\n"
    '            hint = ("本期没有用量" if self._view_idx != 2\n'
    '                    else "本期还没有速度采样")'
)
new2 = (
    "        if not rows:\n"
    "            if self._search_q:\n"
    '                hint = f"没有匹配「{self._search_q}」的行"\n'
    '            elif self._view_idx != 2:\n'
    '                hint = "本期没有用量"\n'
    "            else:\n"
    '                hint = "本期还没有速度采样"'
)
assert old2 in src
src = src.replace(old2, new2, 1)

p.write_text(src, encoding="utf-8")
print("patch10b ok")
