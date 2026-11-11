"""配色与字体 —— Netcatty / shadcn 风格的中性炭黑 + emerald 强调。

设计基调
--------
* **中性炭黑，不是蓝板岩**：底色 #1B1B1B、卡片 #242424、悬浮 #2D2D2D，
  层次靠亮度差 + 一像素描边堆出来，不再往蓝里偏。
* **单一强调色** #0FB77F（emerald）：主按钮、选中态、正向趋势、焦点边框。
  其余颜色只出现在两类地方：工具的品牌色图标块、语义状态色（成功/警告/失败）。
* **彩色图标块**：列表每一行左侧是一个 30px 圆角色块 + 白色缩写，
  对应 Netcatty host 卡片那种「颜色即身份」的读法，而不是给整行上色。
* **文字三级**：#F5F5F5 / #C4C0C8 / #8F8C93（后两级带一点点紫，和参考一致）。
* **数字等宽**：Consolas；界面正文 Microsoft YaHei UI（Mona Sans 系统里没有，
  中文字重也靠它）。
"""
from __future__ import annotations

# ---------------------------------------------------------------- 底层（中性炭黑）
BASE = "#1B1B1B"        # 窗口底色（最深）
SIDEBAR = "#202020"     # 左侧导航栏（比内容区略沉一点）
SURFACE = "#242424"     # 卡片面
SURFACE_2 = "#2D2D2D"   # 输入框 / 次级面 / 分段控件底
SURFACE_3 = "#3A3A3A"   # 选中态 / 悬停高亮
LINE = "#2C2C2C"        # 分隔线
LINE_2 = "#3D3D3D"      # 强描边 / 控件边框

# ---------------------------------------------------------------- 文字
TEXT = "#F5F5F5"        # 主文字
TEXT_2 = "#C4C0C8"      # 次要文字
TEXT_3 = "#8F8C93"      # 弱文字（标签、说明）

# ---------------------------------------------------------------- 强调与语义
ACCENT = "#0FB77F"      # 主强调 / 主按钮 / 选中态
ACCENT_HOVER = "#14C68A"  # 主按钮悬停
ACCENT_DIM = "#0B9B69"  # 主按钮按下 / 深一档
OK = "#0FB77F"          # 正常
WARN = "#F0A93B"        # 预警
DANGER = "#EF4444"      # 失败 / 危险

# 指标卡左侧的小图标块用「低饱和的语义色」，不是整卡染色
COST = "#F0A93B"        # 成本（琥珀）
LATENCY = "#6AA9FF"     # 首字（蓝）
SPEED = "#B08CFF"       # 吞吐（紫）

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
    """把颜色压暗，用作该色块的底色（比直接加透明度更可控）。"""
    return mix(surface, color, t)


def alpha(color: str, surface: str = BASE, t: float = 0.18) -> str:
    """在指定底色上模拟半透明（GDI 没有 alpha 通道）。"""
    return mix(surface, color, t)