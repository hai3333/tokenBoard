"""深色仪表盘配色与字体。

设计基调
--------
* **不是灰阶，是蓝板岩**：底色 / 卡面 / 分隔线都往蓝里偏一点点（#0C1220 → #151E2E），
  纯中性灰在深色下会显得脏、发闷，偏蓝才有"屏幕发光"的感觉。
* **文字三级，但最弱那级也不能太暗**：次级标签要读得清，
  所以 TEXT_3 保持在 #7285A3 上下（对卡面约 4.6:1 对比度）。
* **数字一律用等宽字体**（Consolas），读数能上下对齐，像仪器面板。
* **整体走单色白**（需求：桌面小框和主面板一律白色）。
  工具之间、指标之间不再靠颜色区分，改由字号 / 粗细 / 位置拉层次：
  品牌色数据仍留在 APP_META 里当参考，但界面不上色。
* 只保留**语义色**（正常绿 / 预警琥珀 / 失败红），它们表示状态，不是装饰。
"""
from __future__ import annotations

# ---------------------------------------------------------------- 底层（蓝板岩）
BASE = "#0C1220"        # 窗口底色
SURFACE = "#151E2E"     # 卡片面
SURFACE_2 = "#1C2739"   # 次级面 / 分段控件底
SURFACE_3 = "#26344B"   # 选中态 / 悬停高亮
LINE = "#202B3E"        # 分隔线
LINE_2 = "#35435C"      # 强描边 / 仪表轨道

# ---------------------------------------------------------------- 文字
TEXT = "#ECF1FA"        # 主文字
TEXT_2 = "#A3B2CB"      # 次要文字
TEXT_3 = "#7285A3"      # 弱文字（标签、说明）—— 比中性灰更亮、更蓝

# ---------------------------------------------------------------- 语义
OK = "#3FD9A0"          # 正常（偏青的绿，在蓝底上更透）
WARN = "#FFB84D"        # 预警
DANGER = "#FF6B6B"      # 超限 / 失败

# 装饰性颜色一律白色：强调、指标身份色、工具色都不再各占一色。
# 层次改由字号/粗细/位置承担，避免界面变成红绿灯。
ACCENT = "#FFFFFF"      # 主强调（用量 / 趋势 / 选中态 / 品牌条）
COST = "#FFFFFF"        # 成本
LATENCY = "#FFFFFF"     # 首字
SPEED = "#FFFFFF"       # 吞吐

# ---------------------------------------------------------------- 字体
FONT = "Microsoft YaHei UI"
FONT_NUM = "Consolas"   # 数字 / 读数


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgba(h: str, a: int = 255) -> tuple[int, int, int, int]:
    return hex_to_rgb(h) + (a,)  # type: ignore[return-value]


def mix(a: str, b: str, t: float) -> str:
    """两色线性混合，t=0 取 a，t=1 取 b。"""
    ra, ga, ba = hex_to_rgb(a)
    rb, gb, bb = hex_to_rgb(b)
    return "#{:02x}{:02x}{:02x}".format(
        int(ra + (rb - ra) * t),
        int(ga + (gb - ga) * t),
        int(ba + (bb - ba) * t),
    )


def tint(color: str, surface: str = SURFACE, t: float = 0.28) -> str:
    """把品牌色压暗，用作该色块的底色（比直接加透明度更可控）。"""
    return mix(surface, color, t)