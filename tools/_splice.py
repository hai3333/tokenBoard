#!/usr/bin/env python3
"""把新的绘制代码块拼进 panel.py（替换旧的 draw ~ _footer_msg 段）。"""
import io
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PANEL = r"D:\个人资料\项目\token看板\tokenboard\ui\panel.py"
NEW = r"D:\个人资料\项目\token看板\tools\_new_drawing.py"

src = io.open(PANEL, encoding="utf-8", newline="").read()
new = io.open(NEW, encoding="utf-8", newline="").read()

start_marker = "    def draw(self, c: Canvas):"
end_marker = "    def _jump_to_app(self, app: str) -> None:"

i = src.index(start_marker)
j = src.index(end_marker)

# 结尾保持 end_marker 之前的空行结构
out = src[:i] + new.rstrip("\n") + "\n\n" + src[j:]

io.open(PANEL, "w", encoding="utf-8", newline="").write(out)
print(f"已替换 {len(src)} -> {len(out)} 字节")
print(f"旧块 {j - i} 字符，新块 {len(new)} 字符")
