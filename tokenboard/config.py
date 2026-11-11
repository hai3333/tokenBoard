"""路径与常量配置。"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "TokenBoard"

HOME = Path(os.path.expanduser("~"))


def _data_dir() -> Path:
    """插件自身的数据目录（数据库 / 缓存 / 日志）。"""
    base = os.environ.get("TOKENBOARD_HOME")
    if base:
        return Path(base).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or str(HOME / "AppData/Local")
        return Path(root) / "TokenBoard"
    return HOME / ".tokenboard"


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "tokenboard.db"
LOG_PATH = DATA_DIR / "tokenboard.log"
ASSET_DIR = DATA_DIR / "assets"
WIDGET_STATE_PATH = DATA_DIR / "widget.json"   # 桌面小框的位置等状态
SYNC_CONFIG_PATH = DATA_DIR / "sync.json"      # WebDAV 同步配置（密码经 DPAPI 加密）


# ---------------------------------------------------------------- 采集源路径
CLAUDE_DIR = HOME / ".claude" / "projects"
CODEX_DIR = HOME / ".codex" / "sessions"
MCODEDB = HOME / ".minimax" / "v2" / "sqlite" / "runtime-state.sqlite"
OPENCODE_DB = HOME / ".local" / "share" / "opencode" / "opencode.db"
ZCODE_DIR = HOME / ".zcode" / "cli" / "rollout"
DSH_DIR = HOME / ".dsh" / "sessions"

# 价格表（随插件分发，也可从 CC Switch 的 model_pricing 导入）
PRICING_PATH = Path(__file__).with_name("data") / "pricing.json"

# 成本按美元结算（各家官方价都是 USD），界面额外折一个人民币参考值。
# 汇率会浮动，用环境变量覆盖就行，不必为了它改代码。
CNY_RATE = float(os.environ.get("TOKENBOARD_CNY_RATE") or 7.2)


# ---------------------------------------------------------------- 应用元信息
# key: 内部 app id；value: 展示信息
# color 里保留了各家真实品牌色，但只是**参考数据**：界面整体走白色系，
# 不再按品牌给工具上色（app_color 统一返回白），工具靠名字和位置区分。
APP_META: dict[str, dict] = {
    "claude": {"label": "Claude Code", "short": "Claude", "color": "#D97757", "icon": "CC"},
    "codex": {"label": "Codex CLI", "short": "Codex", "color": "#10A37F", "icon": "CX"},
    "mcode": {"label": "MiniMax Code", "short": "MiniMax", "color": "#7C5CFF", "icon": "MM"},
    "opencode": {"label": "OpenCode", "short": "OpenCode", "color": "#F2A541", "icon": "OC"},
    "zcode": {"label": "ZCode", "short": "ZCode", "color": "#EC4899", "icon": "ZC"},
    "dsh": {"label": "DeepSeek Harness", "short": "DeepSeek", "color": "#3B82F6", "icon": "DS"},
}

APP_ORDER = list(APP_META.keys())


def app_label(app: str) -> str:
    return APP_META.get(app, {}).get("label", app)


def app_color(app: str) -> str:
    """工具的识别色：列表左侧那个图标块用它。

    配色走 Netcatty 那套逻辑 —— 颜色是「身份标识」而不是装饰：
    每个工具一个品牌色小块，界面其余部分保持中性炭黑。
    """
    return APP_META.get(app, {}).get("color", "#8F8C93")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
