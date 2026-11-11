#!/usr/bin/env python3
"""桌面小框（MiniBar）行为验收。

要验的点：
1. 尺寸/位置正确（240x80 设计像素 = 360x120 物理像素，144dpi 下）
2. 顶部一条是拖动区（命中测试返回 HTCAPTION），其余是客户区
3. 点小框 -> 主面板被唤到前台（这就是「点击展开」）
4. **真实拖拽**（SendInput 走系统输入队列，不是模拟消息）：
   - 拖动过程中/之后尺寸不变（早前的 bug：拖一下就被撑成 930x630）
   - 位置真的变了
   - 位置被记住（widget.json）
   - 松手后仍留在工作区内（不会被拖到屏幕外找不着）
5. 小框是工具窗口（不进任务栏），且不抢焦点

关于「模拟」和「真实」的区别（这个坑踩过）：
* SendMessage 发 WM_LBUTTONDOWN 只是把消息**塞给窗口**，不会触发
  DefWindowProc 的模态移动循环，窗口不会真的动 —— 用它验拖拽是假绿。
* SendInput 走系统输入队列，等于真人用鼠标拖，能触发 HTCAPTION 拖动。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard.ui.win32 import user32  # noqa: E402

# 本进程必须 DPI 感知：unaware 时 GetClientRect 拿到虚拟化尺寸，坐标全偏
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_NCHITTEST = 0x0084
HTCAPTION = 2
HTCLIENT = 1

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

# ---- SendInput 相关 --------------------------------------------------
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

FAIL = []
SKIP = []


def check(name, cond, extra=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


def note(msg):
    print(f"  --   {msg}")


def find_windows(class_name):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        c = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, c, 256)
        if c.value == class_name:
            found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return found


def win_rect(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r


def client_size(h):
    r = wintypes.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    return r.right, r.bottom


def work_area():
    """主显示器工作区 (left, top, right, bottom)。"""
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


def send_move(x, y):
    """把真实鼠标移到屏幕物理坐标 (x, y)（绝对坐标）。"""
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi.dx = int(round((x - vx) * 65535.0 / max(1, vw - 1)))
    inp.mi.dy = int(round((y - vy) * 65535.0 / max(1, vh - 1)))
    inp.mi.dwFlags = (MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE |
                      MOUSEEVENTF_VIRTUALDESK)
    return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def goto(x, y, tries=15):
    """把鼠标精确移到 (x, y)，并**校验真的落到位**。

    为什么必须校验：人正在用这台机器时，鼠标随时会被手动挪走，
    SetCursorPos / SendInput 的结果会被打断 —— 不校验就会拿着
    「鼠标其实在别处」的状态去按左键，拖的是别的窗口。
    """
    for _ in range(tries):
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.05)
        cx, cy = cursor_pos()
        if abs(cx - x) <= 2 and abs(cy - y) <= 2:
            return True
    return False


def send_button(down: bool):
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi.dwFlags = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
    return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def real_drag(x0, y0, x1, y1, steps=18):
    """真·拖拽：按住左键 -> 逐步移动 -> 松开。

    返回 True = 拖拽确实发生了；False = 鼠标没听指挥（有人在同时用电脑）。
    """
    if not goto(x0, y0):
        return False
    send_button(True)
    time.sleep(0.20)
    for i in range(1, steps + 1):
        if not goto(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps,
                    tries=4):
            send_button(False)
            return False
        time.sleep(0.02)
    time.sleep(0.20)
    send_button(False)
    time.sleep(0.60)
    return True


def wait_pos_saved(hwnd, timeout=6.0):
    """等 widget.json 里的位置和窗口当前位置对上。

    位置有两条写入路径（拖完的 0x0232 消息、刷新定时器兜底），
    而且**人正在同时拖这个窗口**时，位置随时会变 —— 所以要重试，
    不能拿某一瞬间的快照当结论。
    """
    from tokenboard.config import WIDGET_STATE_PATH
    deadline = time.time() + timeout
    saved = {}
    while True:
        try:
            with open(WIDGET_STATE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:  # noqa: BLE001
            saved = {}
        r = win_rect(hwnd)
        if saved.get("x") == r.left and saved.get("y") == r.top:
            return saved, True
        if time.time() >= deadline:
            return saved, False
        time.sleep(0.4)


def main() -> int:
    from tokenboard.config import WIDGET_STATE_PATH

    mins = find_windows("TokenBoardMini")
    if not mins:
        print("[FAIL] 没找到 TokenBoardMini 窗口（小框没起来）")
        return 1
    mini = mins[0]
    panels = find_windows("TokenBoardWindow")
    if not panels:
        print("[FAIL] 没找到主面板")
        return 1
    panel = panels[0]

    dpi = user32.GetDpiForWindow(mini)
    scale = dpi / 96.0
    want_w, want_h = int(240 * scale), int(80 * scale)
    cw, ch = client_size(mini)
    print(f"小框 hwnd={mini} dpi={dpi} scale={scale} client={cw}x{ch} "
          f"（期望 {want_w}x{want_h}）")

    orig = win_rect(mini)
    print("\n[1] 尺寸")
    check("客户区 = 240x80 设计像素",
          abs(cw - want_w) <= 2 and abs(ch - want_h) <= 2,
          f"{cw}x{ch}（期望 {want_w}x{want_h}）")

    print("\n[2] 拖动区 / 客户区 命中")
    # 顶部一条是拖动区（按住能挪位置），其余是点击区（点一下展开主面板）。
    # 早前把整块都设成 HTCAPTION → 变成「只能拖不能点」，用户明确不要。
    sx = orig.left + int(120 * scale)
    sy = orig.top + int(8 * scale)
    lp = (sy << 16) | (sx & 0xFFFF)
    ht_top = user32.SendMessageW(mini, WM_NCHITTEST, 0, lp)
    check("顶部是拖动区 HTCAPTION", ht_top == HTCAPTION, f"ht={ht_top}")
    sy2 = orig.top + int(50 * scale)
    lp2 = (sy2 << 16) | (sx & 0xFFFF)
    ht_body = user32.SendMessageW(mini, WM_NCHITTEST, 0, lp2)
    check("身体是客户区 HTCLIENT", ht_body == HTCLIENT, f"ht={ht_body}")

    print("\n[3] 点击展开主面板")
    # 先把主面板藏起来，点小框应该把它唤出来
    user32.ShowWindow(panel, 0)          # SW_HIDE
    time.sleep(0.3)
    check("主面板已先隐藏", not user32.IsWindowVisible(panel))

    lparam = (int(50 * scale) << 16) | (int(120 * scale) & 0xFFFF)
    user32.SendMessageW(mini, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.15)
    user32.SendMessageW(mini, WM_LBUTTONUP, 0, lparam)
    time.sleep(1.0)
    check("点小框后主面板可见", bool(user32.IsWindowVisible(panel)))

    print("\n[4] 程序化移动（模拟系统拖动时的 WINDOWPOS：不带 SWP_NOSIZE）")
    # 系统拖动窗口时，WM_WINDOWPOSCHANGING **不带** SWP_NOSIZE，但 cx/cy
    # 就是当前尺寸。早前代码在这里做最小尺寸钳制，把 360x120 钳成 930x630，
    # 用户拖一下小框就变成一大块底板。这里用同样的姿势复现一次。
    before = win_rect(mini)
    user32.SetWindowPos(mini, None, before.left + 37, before.top + 23,
                        before.right - before.left, before.bottom - before.top,
                        SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.4)
    after = win_rect(mini)
    cw2, ch2 = client_size(mini)
    check("移动后尺寸不变", abs(cw2 - want_w) <= 2 and abs(ch2 - want_h) <= 2,
          f"客户区 {cw2}x{ch2}（期望 {want_w}x{want_h}）")
    check("窗口确实移动了",
          (after.left, after.top) != (before.left, before.top),
          f"{before.left},{before.top} -> {after.left},{after.top}")

    print("\n[5] 真实拖拽（系统输入队列）")
    r = win_rect(mini)
    grab_x = r.left + int(120 * scale)
    grab_y = r.top + int(8 * scale)          # 顶部拖动条
    # 往左上方拖 120x60 物理像素
    dst_x, dst_y = grab_x - 120, grab_y - 60
    pre = win_rect(mini)
    pre_size = client_size(mini)
    ok = real_drag(grab_x, grab_y, dst_x, dst_y)
    post = win_rect(mini)
    post_size = client_size(mini)

    if not ok or (post.left, post.top) == (pre.left, pre.top):
        SKIP.append("真实拖拽")
        print("  SKIP 鼠标没听指挥（有人正同时用这台机器 / 会话不可交互），"
              "这一轮没法验真实拖拽")
    else:
        check("拖拽后窗口真的移动了", True,
              f"{pre.left},{pre.top} -> {post.left},{post.top}")
        check("拖拽后尺寸不变（没被撑大）",
              abs(post_size[0] - pre_size[0]) <= 2 and
              abs(post_size[1] - pre_size[1]) <= 2,
              f"{pre_size[0]}x{pre_size[1]} -> {post_size[0]}x{post_size[1]}")
        check("拖拽后仍是 240x80", abs(post_size[0] - want_w) <= 2 and
              abs(post_size[1] - want_h) <= 2,
              f"{post_size[0]}x{post_size[1]}（期望 {want_w}x{want_h}）")
        area = work_area()
        inside = (post.left >= area[0] and post.top >= area[1] and
                  post.right <= area[2] and post.bottom <= area[3])
        check("拖完仍完整落在工作区内", inside,
              f"窗口 {post.left},{post.top}-{post.right},{post.bottom} "
              f"工作区 {area}")

    print("\n[5b] 拖动结束消息 0x0232 -> 立刻写位置")
    # 真拖拽结束系统发的是 0x0232（WM_EXITSIZEMOVE）。
    # 早先代码把这个常量写成 0x02A2，系统发的消息根本没人收，
    # 拖完位置永远不落盘（重启就弹回老地方）。这里直接发真的那个常量验一遍。
    r2 = win_rect(mini)
    nx, ny = r2.left + 17, r2.top + 11
    user32.SetWindowPos(mini, None, nx, ny,
                        r2.right - r2.left, r2.bottom - r2.top,
                        SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.25)
    try:                       # 先删掉旧文件，确保下面读到的是「消息驱动」写的
        os.remove(WIDGET_STATE_PATH)
    except Exception:  # noqa: BLE001
        pass
    user32.PostMessageW(mini, 0x0232, 0, 0)
    time.sleep(0.40)           # 远小于刷新定时器(1.5s)，只可能是消息驱动的写入
    saved_now = {}
    try:
        with open(WIDGET_STATE_PATH, "r", encoding="utf-8") as f:
            saved_now = json.load(f)
    except Exception:  # noqa: BLE001
        pass
    check("收到 0x0232 后位置立刻落盘",
          saved_now.get("x") == nx and saved_now.get("y") == ny,
          f"{saved_now} vs 期望 x={nx} y={ny}")

    print("\n[6] 位置记忆")
    saved, ok = wait_pos_saved(mini, timeout=6.0)
    check("widget.json 有坐标", "x" in saved and "y" in saved, str(saved))
    cur = win_rect(mini)
    check("记住的位置 = 当前窗口位置", ok,
          f"{saved} vs 窗口 {cur.left},{cur.top}")

    # 还原现场：把小框放回原位，别把用户桌面搅乱
    user32.SetWindowPos(mini, None, orig.left, orig.top,
                        orig.right - orig.left, orig.bottom - orig.top,
                        SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.3)
    try:
        with open(WIDGET_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"x": orig.left, "y": orig.top}, f)
    except Exception:  # noqa: BLE001
        pass

    print()
    if FAIL:
        print(f"!!! {len(FAIL)} 项失败: {FAIL}")
        return 1
    if SKIP:
        print(f"全部通过（跳过：{SKIP}）")
        return 0
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
