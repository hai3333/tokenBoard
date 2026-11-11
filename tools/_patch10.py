import pathlib
p = pathlib.Path(r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py")
src = p.read_text(encoding="utf-8")

# 1) 页脚提示改为右对齐贴在状态消息左边，且只在有空间时画（避免和圆点撞车）
old = """        # 中部：快捷键提示（小号暗字，不抢状态圆点）
        hint = "1-4 切视图 · 滚轮滚动 · R 刷新"
        hw, _ = c.measure(hint, self.f_tiny)
        c.text(WIN_W / 2 - hw / 2, yy + 1, hw, 16, hint, self.f_tiny, TEXT_3,
               align=DT_C | DT_VC | DT_SL)

        # 右侧：更新时刻，前面加一个极小的状态灯（有错就变红）
        msg = self._footer_msg()"""
new = """        # 快捷键提示（小号暗字）：贴在状态消息左侧，空间不够就不画
        hint = "1-4 切视图 · 滚轮 · R 刷新"
        hw, _ = c.measure(hint, self.f_tiny)
        hint_x = WIN_W - PAD - 220 - 10 - hw
        if hint_x > x + 10:
            c.text(hint_x, yy + 1, hw, 16, hint, self.f_tiny, TEXT_3,
                   align=DT_L | DT_VC | DT_SL)

        # 右侧：更新时刻，前面加一个极小的状态灯（有错就变红）
        msg = self._footer_msg()"""
assert old in src
src = src.replace(old, new, 1)

# 2) 搜索无结果时给出专属提示，别跟「本期没有用量」混在一起
old2 = """        if not rows:
            hint = ("本期没有用量" if self._view_idx != 2
                    else "当前没有速度样本")"""
new2 = """        if not rows:
            if self._search_q:
                hint = f"没有匹配「{self._search_q}」的行"
            elif self._view_idx != 2:
                hint = "本期没有用量"
            else:
                hint = "当前没有速度样本\""""
assert old2 in src
src = src.replace(old2, new2, 1)

p.write_text(src, encoding="utf-8")
print("footer/empty ok")
