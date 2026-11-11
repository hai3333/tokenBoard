"""开机自启：往「启动」文件夹丢一个静默启动脚本。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import APP_NAME

STARTUP_DIR = Path(
    os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
) / "Microsoft/Windows/Start Menu/Programs/Startup"


def _pythonw() -> str:
    """找 pythonw.exe（无控制台窗口）。"""
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    if cand.exists():
        return str(cand)
    return str(exe)


def _script_body(project_dir: Path) -> str:
    return (
        "@echo off\n"
        f'cd /d "{project_dir}"\n'
        f'start "" "{_pythonw()}" -m tokenboard.app\n'
    )


def install(project_dir: Path | None = None) -> Path:
    project_dir = Path(project_dir or Path(__file__).resolve().parents[1])
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    target = STARTUP_DIR / f"{APP_NAME}.bat"
    target.write_text(_script_body(project_dir), encoding="utf-8")
    return target


def uninstall() -> bool:
    target = STARTUP_DIR / f"{APP_NAME}.bat"
    if target.exists():
        target.unlink()
        return True
    return False


def is_installed() -> bool:
    return (STARTUP_DIR / f"{APP_NAME}.bat").exists()
