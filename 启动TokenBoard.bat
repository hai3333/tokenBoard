@echo off
REM ============================================================
REM  TokenBoard - 本机 AI IDE Token 消耗看板
REM  启动桌面端（托盘 + 面板）
REM ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [TokenBoard] 找不到 python，请先安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
)

set "PYTHONIOENCODING=utf-8"
python -m tokenboard.app %*
if errorlevel 1 (
    echo.
    echo [TokenBoard] 启动失败，详见 %LOCALAPPDATA%\TokenBoard\tokenboard.log
    pause
)
endlocal
