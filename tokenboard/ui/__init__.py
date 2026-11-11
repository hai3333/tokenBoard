"""桌面 UI 包（原生 Win32 实现，无第三方 GUI 依赖）。"""
from .panel import Panel, fmt_tokens
from .tray import Tray

__all__ = ["Panel", "Tray", "fmt_tokens"]
