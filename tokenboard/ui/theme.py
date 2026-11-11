"""配色与字体 —— 中性炭黑 / 亮色两套，运行时可切，支持跟随系统。

设计基调（参考 Netcatty / shadcn）
----------------------------------
* **两套同源调色板**：暗色是炭黑层级（#1B1B1B → #242424 → #2D2D2D），
  亮色是白灰层级（#F7F7F8 → #FFFFFF → #F4F4F5），层次都靠「亮度差 + 1px 描边」。
* **单一强调色** #0FB77F（emerald）：主按钮、选中态、正向趋势、焦点边框。
* **彩色图标块**：列表每行的品牌色方块，颜色是「身份标识」而不是装饰。
* **文字三级**：主 / 次 / 弱，亮色下把弱文字压到 #8A8A93 保证对比度。

运行时切换
----------
面板/设置窗/小框在 import 时把颜色名复制成了各自的模块变量，所以切主题时
除了改 theme 自己的全局，还要把它们**注册过的模块**里的同名变量一起刷一遍
（`register()` + `apply()`）。绘制代码每次绘制都读模块变量，刷新即生效。

偏好保存在数据库 app_meta 的 `theme` 键：auto / light / dark。
`WM_SETTINGCHANGE`（ImmersiveColorSet）到达时，auto 模式会重新解析一次。
"""
from __future__ import annotations

# ---------------------------------------------------------------- 字体
FONT = "Microsoft YaHei UI"
FONT_NUM = "Consolas"   # 数字 / 读数
RADIUS = 12
RADIUS_SM = 8

# ---------------------------------------------------------------- 暗色
DARK: dict[str, str] = {
    "BASE": "#1B1B1B",          # 窗口底色
    "SIDEBAR": "#202020",       # 左侧导航
    "SURFACE": "#242424",       # 卡片面
    "SURFACE_2": "#2D2D2D",     # 输入框 / 次级面
    "SURFACE_3": "#3A3A3A",     # 选中 / 悬停
    "LINE": "#2C2C2C",          # 分隔线
    "LINE_2": "#3D3D3D",        # 控件边框
    "TEXT": "#F5F5F5",
    "TEXT_2": "#C4C0C8",
    "TEXT_3": "#8F8C93",
    "ACCENT": "#0FB77F",
    "ACCENT_HOVER": "#14C68A",
    "ACCENT_DIM": "#0B9B69",
    "ON_ACCENT": "#06231A",     # 主按钮上的文字
    "OK": "#0FB77F",
    "WARN": "#F0A93B",
    "DANGER": "#EF4444",
    "COST": "#F0A93B",
    "LATENCY": "#6AA9FF",
    "SPEED": "#B08CFF",
    "CARD_LINE": "#2F2F2F",     # 卡片描边
    "CARD_TOP": "#2A2A2A",      # 顶边高光
    "SHADOW": "#141414",
    "ROW_HOVER": "#262626",
    "GRID": "#262626",
    "TRACK": "#2A2A2A",
    "CHART_BAR": "#0E8F63",     # 历史柱
    "CHART_TODAY": "#0FB77F",   # 今天
    "TILE_TEXT": "#FFFFFF",     # 品牌色块上的字
    "TILE_MIX": "0.12",         # 图标块底色向品牌色混合的比例（字符串，避免类型混乱）
}

# ---------------------------------------------------------------- 亮色
LIGHT: dict[str, str] = {
    "BASE": "#F7F7F8",
    "SIDEBAR": "#F0F0F1",
    "SURFACE": "#FFFFFF",
    "SURFACE_2": "#F4F4F5",
    "SURFACE_3": "#E7E7EA",
    "LINE": "#E9E9EC",
    "LINE_2": "#D8D8DE",
    "TEXT": "#18181B",
    "TEXT_2": "#52525B",
    "TEXT_3": "#8A8A93",
    "ACCENT": "#0FB77F",
    "ACCENT_HOVER": "#12C68A",
    "ACCENT_DIM": "#0B9B69",
    "ON_ACCENT": "#FFFFFF",
    "OK": "#0B9B69",
    "WARN": "#C2740A",
    "DANGER": "#DC2626",
    "COST": "#C2740A",
    "LATENCY": "#2563EB",
    "SPEED": "#7C3AED",
    "CARD_LINE": "#E7E7EA",
    "CARD_TOP": "#FFFFFF",
    "SHADOW": "#EFEFF1",
    "ROW_HOVER": "#F4F4F5",
    "GRID": "#EFEFF1",
    "TRACK": "#EFEFF1",
    "CHART_BAR": "#6FCBA8",
    "CHART_TODAY": "#0FB77F",
    "TILE_TEXT": "#FFFFFF",
    "TILE_MIX": "0.10",
}

PALETTES = {"dark": DARK, "light": LIGHT}
_MODULES: list = []
MODE = "dark"


# ---------------------------------------------------------------- 运行时
def register(module) -> None:
    """登记一个「把颜色名复制成了模块全局」的 UI 模块，切主题时一起刷新。"""
    if module is not None and module not in _MODULES:
        _MODULES.append(module)


def system_mode() -> str:
    """Windows 当前的应用主题（读注册表；读不到按暗色）。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        try:
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(val) else "dark"
        finally:
            key.Close()
    except Exception:  # noqa: BLE001
        return "dark"


def resolve(pref: str) -> str:
    """把偏好（auto/light/dark）解析成实际生效的模式。"""
    pref = (pref or "auto").strip().lower()
    if pref in ("light", "dark"):
        return pref
    return system_mode()


def _push(pal: dict[str, str]) -> None:
    globals().update(pal)
    for mod in list(_MODULES):
        for k, v in pal.items():
            try:
                setattr(mod, k, v)
            except Exception:  # noqa: BLE001
                pass


def apply(pref: str = "auto") -> str:
    """应用主题，返回实际生效的模式（dark / light）。"""
    global MODE
    MODE = resolve(pref)
    _push(PALETTES[MODE])
    return MODE


# 启动时先套一份暗色，保证 import 后所有名字都有值
_push(DARK)


# ---------------------------------------------------------------- 工具
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


def tint(color: str, surface: str | None = None, t: float = 0.28) -> str:
    """把颜色压暗/调亮，用作该色块的底色。"""
    return mix(surface or SURFACE, color, t)


def on_color(color: str) -> str:
    """色块上的文字色：亮色块用深色字，暗色块用白字。"""
    r, g, b = hex_to_rgb(color)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#101014" if lum > 0.62 else TILE_TEXT