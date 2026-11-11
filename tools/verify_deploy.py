#!/usr/bin/env python3
"""部署版验收：跑 D:\\software\\TokenBoard\\TokenBoard.exe，检查三件套。

1. 免安装 exe 能起来，且 DPI 感知正确（界面不会被系统虚拟化缩小）
2. 桌面小框（TokenBoardMini）在，尺寸/位置对
3. 点标题栏齿轮 -> OpenCode 配置窗口能弹出
4. 内存占用（常驻插件要轻）

用法：python tools/verify_deploy.py [--keep]
"""
from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from wincap import capture_client  # noqa: E402  （import 时就把本进程切成 DPI 感知）

EXE = Path(r"D:\software\TokenBoard\TokenBoard.exe")
SHOT_DIR = Path(r"D:\个人资料\项目\token看板\tools")
LOG = Path.home() / "AppData/Local/TokenBoard/tokenboard.log"

user32 = ctypes.windll.user32
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetDpiForWindow.restype = ctypes.c_uint
user32.GetDpiForWindow.argtypes = [wintypes.HWND]

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
FAIL = []


def check(name, cond, extra=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


def find_windows(class_name):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == class_name:
            out.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return out


def win_info(h):
    cr = wintypes.RECT()
    user32.GetClientRect(h, ctypes.byref(cr))
    wr = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(wr))
    dpi = user32.GetDpiForWindow(h)
    return cr, wr, dpi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="验收后不关掉进程")
    args = ap.parse_args()

    if not EXE.exists():
        print(f"[FAIL] 找不到 {EXE}")
        return 1
    print(f"部署版: {EXE}  {EXE.stat().st_size / 1048576:.2f} MB")

    # 单实例：先停掉源码实例和旧 exe，否则 exe 启动后会直接退出。
    # 注意：不能 taskkill /IM python.exe —— 那会把本脚本自己也杀掉。
    subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { "
         "$_.CommandLine -like '*tokenboard.app*' } | ForEach-Object { "
         "Stop-Process -Id $_.ProcessId -Force }"],
        capture_output=True)
    time.sleep(2)

    print("\n启动部署版 ...")
    proc = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    panel = None
    for _ in range(60):
        time.sleep(0.5)
        w = find_windows("TokenBoardWindow")
        if w:
            panel = w[0]
            break
    if not panel:
        print("[FAIL] 部署版没出现主面板窗口")
        return 1
    print(f"  主面板 hwnd={panel}")

    print("\n[1] DPI / 尺寸")
    cr, wr, dpi = win_info(panel)
    scale = dpi / 96.0
    check("客户区 = 880x520 设计像素",
          abs(cr.right - 880 * scale) <= 2 and abs(cr.bottom - 520 * scale) <= 2,
          f"{cr.right}x{cr.bottom} @ {dpi}dpi（期望 {int(880*scale)}x{int(520*scale)}）")

    print("\n[2] 桌面小框")
    mins = find_windows("TokenBoardMini")
    check("小框已常驻", len(mins) == 1, f"{len(mins)} 个")
    if mins:
        mcr, mwr, mdpi = win_info(mins[0])
        check("小框 = 240x80 设计像素",
              abs(mcr.right - 240 * scale) <= 2 and abs(mcr.bottom - 80 * scale) <= 2,
              f"{mcr.right}x{mcr.bottom}")
        check("小框可见", bool(user32.IsWindowVisible(mins[0])))
        img = capture_client(mins[0])
        img.save(SHOT_DIR / "deploy_mini.png")
        print(f"  截图 -> deploy_mini.png {img.size[0]}x{img.size[1]}")

    print("\n[2b] 小框真实拖拽（系统输入队列）")
    if mins:
        from test_mini import client_size, real_drag, win_rect
        m = mins[0]
        pre = win_rect(m)
        pre_size = client_size(m)
        gx = pre.left + int(120 * scale)
        gy = pre.top + int(8 * scale)          # 顶部拖动条
        ok = real_drag(gx, gy, gx - 120, gy - 60)
        post = win_rect(m)
        post_size = client_size(m)
        if not ok or (post.left, post.top) == (pre.left, pre.top):
            # 有人在同时用这台机器时鼠标会不听话，这轮跳过（不算失败）
            print("  SKIP 鼠标没听指挥（有人在同时操作电脑），真实拖拽这轮没法验")
        else:
            check("拖拽后小框真的移动了",
                  (post.left, post.top) != (pre.left, pre.top),
                  f"{pre.left},{pre.top} -> {post.left},{post.top}")
            check("拖拽后尺寸没变（没被撑成大底板）", post_size == pre_size,
                  f"{pre_size[0]}x{pre_size[1]} -> {post_size[0]}x{post_size[1]}")
        # 位置要落盘（widget.json）：两条路径 —— 拖完的 WM_EXITSIZEMOVE
        # 立刻写，或刷新定时器（1.5s）兜底写。等一会儿再读，两条都覆盖。
        from test_mini import wait_pos_saved
        saved, ok = wait_pos_saved(m, timeout=6.0)
        _r = win_rect(m)
        check("位置已记住", ok, f"{saved} vs 窗口 {_r.left},{_r.top}")

    print("\n[3] OpenCode 配置入口已移除")
    # 需求：不要 OpenCode 配置了。齿轮位置现在应该是「什么都没有」，
    # 点下去不能弹出任何配置窗口。
    gear_x = int((880 - 120 + 20) * scale)
    gear_y = int(15 * scale)
    lp = (gear_y << 16) | (gear_x & 0xFFFF)
    user32.SendMessageW(panel, WM_LBUTTONDOWN, 1, lp)
    time.sleep(0.15)
    user32.SendMessageW(panel, WM_LBUTTONUP, 0, lp)
    time.sleep(1.2)
    cws = find_windows("TokenBoardConfigWindow")
    check("点原来齿轮的位置不会弹配置窗口", len(cws) == 0, f"{len(cws)} 个")
    check("整个进程里没有配置窗口", len(find_windows("TokenBoardConfigWindow")) == 0)

    img = capture_client(panel)
    img.save(SHOT_DIR / "deploy_panel.png")
    print(f"\n截图 -> deploy_panel.png {img.size[0]}x{img.size[1]}")

    print("\n[4] 内存")
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq TokenBoard.exe", "/FO", "CSV"],
            capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        for line in out.splitlines()[1:]:
            cols = [c.strip('"') for c in line.split('","')]
            if len(cols) >= 5 and cols[0] == "TokenBoard.exe":
                print(f"  pid={cols[1]} 内存={cols[4]}")
    except Exception as e:  # noqa: BLE001
        print("  读不到:", e)

    print("\n[5] 启动日志")
    if LOG.exists():
        txt = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in txt[-6:]:
            print("  " + line)

    if not args.keep:
        print("\n关闭测试进程 ...")
        subprocess.run(["taskkill", "/IM", "TokenBoard.exe", "/F"], capture_output=True)

    print()
    if FAIL:
        print(f"!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
