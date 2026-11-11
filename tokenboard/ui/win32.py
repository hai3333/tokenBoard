"""原生 Win32 封装：窗口 + GDI 绘制。

刻意不依赖 tkinter / Pillow —— 这三个库加起来要吃掉 40MB 内存，
对一个常驻托盘插件太奢侈。Win32 直接画反而更省、更快。

坐标一律用「设计像素」，实际绘制时统一乘以 DPI 缩放系数。
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

# ------------------------------------------------------------------ 常量
WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_POPUP = 0x80000000
WS_OVERLAPPEDWINDOW = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | \
    WS_MINIMIZEBOX | WS_MAXIMIZEBOX
# 自绘标题栏：不要系统标题栏/边框。
# WS_THICKFRAME 是留着让 DWM 画投影和圆角的，实际不可缩放
# （WM_NCHITTEST 一律返回 HTCLIENT/HTCAPTION，边框收不到鼠标）。
WS_FIXED = WS_POPUP | WS_THICKFRAME
# 桌面小框：不要边框、不可缩放，自己整块就是客户区
WS_PLAIN = WS_POPUP
WS_EX_APPWINDOW = 0x00040000   # 让无边框窗口仍然有任务栏按钮
WS_EX_TOOLWINDOW = 0x00000080  # 不在任务栏出现（桌面小框用）
WS_EX_TOPMOST = 0x00000008     # 置顶
WS_EX_LAYERED = 0x00080000     # 分层窗口：可以设整体透明度
LWA_ALPHA = 0x00000002         # SetLayeredWindowAttributes：按整体 alpha 混合
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
WS_VISIBLE = 0x10000000
SW_SHOW = 5
SW_HIDE = 0
CW_USEDEFAULT = -2147483648

# ---- 子控件（原生编辑框）
WS_CHILD = 0x40000000
WS_TABSTOP = 0x00010000
ES_AUTOHSCROLL = 0x0080
ES_AUTOVSCROLL = 0x0040
ES_PASSWORD = 0x0020
ES_MULTILINE = 0x0004
ES_WANTRETURN = 0x1000
EM_SETSEL = 0x00B1
EM_SETPASSWORDCHAR = 0x00CC
EN_CHANGE = 0x0300
WM_CTLCOLOREDIT = 0x0133
WM_CTLCOLORSTATIC = 0x0132
WM_SETFONT = 0x0030
EM_SETMARGINS = 0x00D3      # 输入框内边距（文字不要贴边）
EC_LEFTMARGIN = 0x0001
EC_RIGHTMARGIN = 0x0002

WM_DESTROY = 0x0002
WM_SIZE = 0x0005
WM_PAINT = 0x000F
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_SETCURSOR = 0x0020
WM_GETMINMAXINFO = 0x0024
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCPAINT = 0x0085
WM_NCACTIVATE = 0x0086
WM_SETTINGCHANGE = 0x001A  # 系统设置变化（主题/DPI/颜色）会广播这个消息
WM_WINDOWPOSCHANGING = 0x0046
WM_KEYDOWN = 0x0100
WM_CHAR = 0x0102
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WM_PRINT = 0x0317
WM_PRINTCLIENT = 0x0318
WM_COMMAND = 0x0111
WM_APP = 0x8000
WM_TRAY = 0x8001          # 托盘图标回调消息（tray.py 里注册给 Shell_NotifyIcon）
WM_TIMER = 0x0113
# 拖动/缩放是**成对**的两个消息，真实常量 0x0231 / 0x0232。
# 早先这里把 WM_EXITSIZEMOVE 写成了 0x02A2 —— 系统发的 0x0232 根本没人收，
# 拖完小框永远不写位置（重启就弹回老地方），这个坑查了半天才定位到。
WM_ENTERSIZEMOVE = 0x0231  # 进入拖动/缩放（系统模态循环开始）
WM_EXITSIZEMOVE = 0x0232   # 拖动/缩放结束（拖完小框要记住位置）
WM_MOUSELEAVE = 0x02A3     # 鼠标移出窗口（要 TrackMouseEvent 才会收到）
WM_NCMOUSEMOVE = 0x00A0   # 鼠标在**非客户区**移动（窗口整体当拖动区时走这条）
WM_NCMOUSELEAVE = 0x02A2  # 鼠标移出非客户区
TME_LEAVE = 0x00000002    # TrackMouseEvent 的标志位
TME_NONCLIENT = 0x00000010  # TrackMouseEvent：跟踪非客户区（0x10，不是 0x02）
WM_USER = 0x0400
WM_SETICON = 0x0080

WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

SW_RESTORE = 9
SW_SHOWNA = 8
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
CS_DBLCLKS = 0x0008

IDC_ARROW = 32512
IDC_HAND = 32649
IDC_SIZENWSE = 32642     # 缩放光标：↖↘
IDC_SIZENESW = 32643     # 缩放光标：↗↙
IDC_SIZEWE = 32644       # 缩放光标：↔
IDC_SIZENS = 32645       # 缩放光标：↕
IDC_SIZEALL = 32646      # 四向移动光标（拖动窗口）

HTCLIENT = 1
HTCAPTION = 2
HTSYSMENU = 4
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

TRANSPARENT = 1
OPAQUE = 2
ANTIALIASED_QUALITY = 4
CLEARTYPE_QUALITY = 5

TA_LEFT = 0
TA_CENTER = 1
TA_RIGHT = 2
TA_TOP = 0
TA_VCENTER = 6
TA_BOTTOM = 8

DT_LEFT = 0x00000000
DT_CENTER = 0x00000001
DT_RIGHT = 0x00000002
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020
DT_NOPREFIX = 0x00000800
DT_END_ELLIPSIS = 0x00008000
DT_CALCRECT = 0x00000400

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NOTIFYICON_VERSION_4 = 4

WM_CONTEXTMENU_ID = 1001
WM_SHOW_ID = 1002
WM_REFRESH_ID = 1003
WM_QUIT_ID = 1004

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100


# ------------------------------------------------------------------ 工具
def rgb(hex_color: str) -> int:
    """#RRGGBB -> COLORREF(0x00BBGGRR)"""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def enable_dpi_awareness() -> float:
    """开启 Per-Monitor DPI，返回缩放系数（96dpi -> 1.0）。"""
    ok = _set_process_dpi_aware()
    state = dpi_awareness_state()
    _tlog(f"[dpi] 切换={'成功' if ok else '失败'} 感知={state}")
    try:
        dpi = user32.GetDpiForSystem()
        return (dpi or 96) / 96.0
    except Exception:  # noqa: BLE001
        return 1.0


def _set_process_dpi_aware() -> bool:
    """按优先级尝试设置进程 DPI 感知，返回进程最终是否处于感知状态。

    顺序：per-monitor v2 -> per-monitor -> system aware。
    打包后的 exe 自带 manifest（已声明 dpiAware/pm），这时第一个调用会
    返回 FALSE（ERROR_ACCESS_DENIED）—— 但进程其实已经是感知状态，
    所以最后统一按实际感知状态判定，而不是看那几次调用的返回值。
    """
    for ctx in (-4, -3):        # PER_MONITOR_AWARE_V2 / PER_MONITOR_AWARE
        try:
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(ctx)):
                return True
        except Exception:  # noqa: BLE001
            break
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass
    # 调用返回 FALSE 不代表没生效（manifest 可能已经声明了），
    # 一律以 GetAwarenessFromDpiAwarenessContext 的实际结果为准。
    return dpi_awareness_state() != "UNAWARE"


def dpi_awareness_state() -> str:
    """当前进程的 DPI 感知状态（诊断用）。

    SetProcessDpiAwarenessContext 失败时**不抛异常**，只返回 FALSE。
    打包后的 exe 自带 manifest（已声明 dpiAware）时第一个调用就会失败，
    这时进程其实已经是感知状态 —— 但不查一下就永远不知道到底处在哪种。
    """
    try:
        ctx = int(user32.GetThreadDpiAwarenessContext())
    except Exception:  # noqa: BLE001
        return "unknown"
    # GetThreadDpiAwarenessContext 返回的可能是系统共享上下文句柄（不是 -1~-4），
    # 所以再问一次 GetAwarenessFromDpiAwarenessContext 拿标准枚举。
    try:
        aware = int(user32.GetAwarenessFromDpiAwarenessContext(
            ctypes.c_void_p(ctx & 0xFFFFFFFFFFFFFFFF)))
    except Exception:  # noqa: BLE001
        aware = -1
    name = {0: "UNAWARE", 1: "SYSTEM_AWARE", 2: "PER_MONITOR"}.get(
        aware, f"UNKNOWN({aware})")
    return name if aware >= 0 else name


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND,
                                           wintypes.UINT, wintypes.WPARAM,
                                           wintypes.LPARAM)),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", wintypes.RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", wintypes.POINT), ("ptMaxSize", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT), ("ptMinTrackSize", wintypes.POINT),
                ("ptMaxTrackSize", wintypes.POINT)]


class TEXTMETRIC(ctypes.Structure):
    """GDI 字体度量：用来量出「一个字到底多高」。"""

    _fields_ = [
        ("tmHeight", ctypes.c_long), ("tmAscent", ctypes.c_long),
        ("tmDescent", ctypes.c_long), ("tmInternalLeading", ctypes.c_long),
        ("tmExternalLeading", ctypes.c_long), ("tmAveCharWidth", ctypes.c_long),
        ("tmMaxCharWidth", ctypes.c_long), ("tmWeight", ctypes.c_long),
        ("tmOverhang", ctypes.c_long), ("tmDigitizedAspectX", ctypes.c_long),
        ("tmDigitizedAspectY", ctypes.c_long), ("tmFirstChar", wintypes.WCHAR),
        ("tmLastChar", wintypes.WCHAR), ("tmDefaultChar", wintypes.WCHAR),
        ("tmBreakChar", wintypes.WCHAR), ("tmItalic", ctypes.c_byte),
        ("tmUnderlined", ctypes.c_byte), ("tmStruckOut", ctypes.c_byte),
        ("tmPitchAndFamily", ctypes.c_byte), ("tmCharSet", ctypes.c_byte),
    ]


class WINDOWPOS(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("hwndInsertAfter", wintypes.HWND),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("cx", ctypes.c_int),
        ("cy", ctypes.c_int),
        ("flags", wintypes.UINT),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


class TRACKMOUSEEVENT(ctypes.Structure):
    """TrackMouseEvent 参数 —— 用来收 WM_MOUSELEAVE。"""
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("hwndTrack", wintypes.HWND),
        ("dwHoverTime", wintypes.DWORD),
    ]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    """WM_NCCALCSIZE 的参数。

    rgrc[0] 客户区（窗口坐标）/ rgrc[1] 客户区（屏幕坐标）/ rgrc[2] 客户区（父窗口坐标）。
    三个都要改 —— 只改 rgrc[0] 的话，带边框的窗口会**停在屏幕 (0,0)**：
    界面左上角会被裁掉一块（配置窗口建在 200,120 时正好裁掉标题栏和左侧列表）。
    """
    _fields_ = [
        ("rgrc", wintypes.RECT * 3),
        ("ppos", ctypes.c_void_p),
    ]



WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                              wintypes.WPARAM, wintypes.LPARAM)

# 调试用：设 TOKENBOARD_TRACE=1 后把收到的消息记到 %LOCALAPPDATA%\TokenBoard\trace.log
_TRACE = bool(os.environ.get("TOKENBOARD_TRACE"))

_MSG_NAMES = {
    0x0002: "WM_DESTROY", 0x000F: "WM_PAINT", 0x0010: "WM_CLOSE",
    0x0014: "WM_ERASEBKGND", 0x0020: "WM_SETCURSOR", 0x0024: "WM_GETMINMAXINFO",
    0x0100: "WM_KEYDOWN", 0x0111: "WM_COMMAND", 0x0112: "WM_SYSCOMMAND",
    0x0113: "WM_TIMER", 0x0200: "WM_MOUSEMOVE", 0x0201: "WM_LBUTTONDOWN",
    0x0202: "WM_LBUTTONUP", 0x020A: "WM_MOUSEWHEEL", 0x0080: "WM_SETICON",
    0x0018: "WM_SHOWWINDOW", 0x0006: "WM_ACTIVATE", 0x0019: "WM_MOVE",
    0x0005: "WM_SIZE", 0x0083: "WM_NCCALCSIZE", 0x0084: "WM_NCHITTEST",
    0x0047: "WM_WINDOWPOSCHANGED", 0x0231: "WM_ENTERSIZEMOVE",
    0x0232: "WM_EXITSIZEMOVE", 0x00A0: "WM_NCMOUSEMOVE",
    0x02A2: "WM_NCMOUSELEAVE",
}
_SC_NAMES = {0xF060: "SC_CLOSE", 0xF020: "SC_MINIMIZE", 0xF030: "SC_MAXIMIZE",
             0xF010: "SC_MOVE", 0xF023: "SC_RESTORE"}


def _trace_path() -> str:
    from ..config import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(DATA_DIR / "trace.log")


def _trace(win, msg, wparam, lparam) -> None:
    try:
        name = _MSG_NAMES.get(msg, f"0x{msg:04X}")
        extra = ""
        if msg == 0x0112:
            extra = f" cmd={_SC_NAMES.get(wparam & 0xFFF0, hex(wparam & 0xFFF0))}"
        elif msg == 0x020A:
            raw = (wparam >> 16) & 0xFFFF
            extra = f" raw={raw} signed={ctypes.c_short(raw).value}"
        elif msg == 0x0200:
            extra = (f" at ({ctypes.c_short(lparam & 0xFFFF).value},"
                     f"{ctypes.c_short((lparam >> 16) & 0xFFFF).value})")
        elif msg == 0x0113:
            extra = f" tid={wparam}"
        with open(_trace_path(), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')}.{int(time.time() % 1 * 1000):03d} "
                    f"{name}{extra}\n")
    except Exception:  # noqa: BLE001
        pass


def _tlog(text: str) -> None:
    """往 trace.log 追加一行尺寸/状态说明（仅 TOKENBOARD_TRACE=1 时生效）。"""
    if not _TRACE:
        return
    try:
        with open(_trace_path(), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')}.{int(time.time() % 1 * 1000):03d} "
                    f"{text}\n")
    except Exception:  # noqa: BLE001
        pass


def _make_wndproc():
    def proc(hwnd, msg, wparam, lparam):
        try:
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        except Exception:  # noqa: BLE001
            return 0
    return WNDPROC(proc)


def _setup_prototypes() -> None:
    """ctypes 默认把返回值/参数当 c_int，64 位句柄会被截断 —— 必须逐个声明。"""
    H, HDC, HB, BR, PEN = (wintypes.HANDLE, wintypes.HDC, wintypes.HBITMAP,
                           wintypes.HBRUSH, wintypes.HANDLE)
    CR, RECTP = wintypes.COLORREF, ctypes.POINTER(wintypes.RECT)

    # ---- user32
    # DPI 感知：失败时只返回 FALSE，必须看返回值
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDPIAware.restype = wintypes.BOOL
    user32.GetThreadDpiAwarenessContext.restype = ctypes.c_ssize_t
    user32.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
    user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.GetWindowDpiAwarenessContext.restype = ctypes.c_int
    user32.GetDpiForWindow.restype = ctypes.c_uint
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForSystem.restype = ctypes.c_uint
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
    user32.GetDC.restype = HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = HDC
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.ReleaseDC.argtypes = [wintypes.HWND, HDC]
    user32.BeginPaint.restype = HDC
    user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    user32.EndPaint.restype = wintypes.BOOL
    user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    user32.DrawTextW.restype = ctypes.c_int
    # 注意：DrawTextW 是 5 个参数 (hdc, text, cchText, lprc, uFormat)，少传一个会错位
    user32.DrawTextW.argtypes = [HDC, wintypes.LPCWSTR, ctypes.c_int, RECTP,
                                 wintypes.UINT]
    user32.FillRect.restype = ctypes.c_int
    user32.FillRect.argtypes = [HDC, RECTP, BR]
    user32.LoadCursorW.restype = H
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.CreateIconIndirect.restype = wintypes.HICON
    user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
    user32.DestroyIcon.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                    ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.restype = wintypes.UINT
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      ctypes.c_void_p]
    user32.CheckMenuRadioItem.restype = wintypes.BOOL
    user32.CheckMenuRadioItem.argtypes = [wintypes.HMENU, wintypes.UINT,
                                          wintypes.UINT, wintypes.UINT,
                                          wintypes.UINT]
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    # 坐标转换必须声明原型：默认按 c_int 传 HWND，64 位句柄被截断，
    # ScreenToClient 会**静默失败**（坐标原样返回），命中测试就全乱了。
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ScreenToClient.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.SetCursor.argtypes = [wintypes.HANDLE]
    user32.SetCursor.restype = wintypes.HANDLE
    user32.GetCursor.restype = wintypes.HANDLE
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT,
                                 ctypes.c_void_p]
    user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    user32.GetWindowRect.argtypes = [wintypes.HWND, RECTP]
    user32.AdjustWindowRectEx.restype = wintypes.BOOL
    user32.AdjustWindowRectEx.argtypes = [RECTP, wintypes.DWORD, wintypes.BOOL,
                                          wintypes.DWORD]
    user32.GetClientRect.argtypes = [wintypes.HWND, RECTP]
    user32.MoveWindow.restype = wintypes.BOOL
    user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.BOOL]
    # HWND 参数不声明原型会被 ctypes 按 c_int 截断（64 位下句柄直接废掉）
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT]
    # 分层窗口的透明度（桌面小框要「透一点」，别像一块实心板子）
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND,
                                                  wintypes.COLORREF,
                                                  ctypes.c_ubyte,
                                                  wintypes.DWORD]
    user32.DefWindowProcW.restype = ctypes.c_longlong
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND,
                                    wintypes.UINT, wintypes.UINT]
    user32.SendMessageW.restype = ctypes.c_longlong
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                 ctypes.POINTER(wintypes.DWORD)]
    # 编辑框相关
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                      ctypes.c_int]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.SetWindowTextW.restype = ctypes.c_bool
    user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.SetFocus.restype = wintypes.HWND
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.GetFocus.restype = wintypes.HWND
    user32.TrackMouseEvent.restype = wintypes.BOOL
    user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]

    # ---- gdi32
    gdi32.CreateCompatibleDC.restype = HDC
    gdi32.CreateCompatibleDC.argtypes = [HDC]
    gdi32.CreateCompatibleBitmap.restype = HB
    gdi32.CreateCompatibleBitmap.argtypes = [HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateBitmap.restype = HB
    gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_void_p]
    gdi32.CreateDIBSection.restype = HB
    gdi32.CreateDIBSection.argtypes = [HDC, ctypes.c_void_p, wintypes.UINT,
                                        ctypes.POINTER(ctypes.c_void_p),
                                        wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateSolidBrush.restype = BR
    gdi32.CreateSolidBrush.argtypes = [CR]
    gdi32.CreatePen.restype = PEN
    gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, CR]
    gdi32.CreateFontW.restype = H
    gdi32.CreateFontW.argtypes = ([ctypes.c_int] * 5 + [ctypes.c_int] * 3
                                  + [wintypes.DWORD] * 5 + [wintypes.LPCWSTR])
    gdi32.GetStockObject.restype = H
    gdi32.GetStockObject.argtypes = [ctypes.c_int]
    gdi32.GetTextMetricsW.argtypes = [HDC, ctypes.POINTER(TEXTMETRIC)]
    gdi32.SelectObject.restype = H
    gdi32.SelectObject.argtypes = [HDC, H]
    gdi32.DeleteObject.argtypes = [H]
    gdi32.DeleteDC.argtypes = [HDC]
    gdi32.GetDeviceCaps.restype = ctypes.c_int
    gdi32.GetDeviceCaps.argtypes = [HDC, ctypes.c_int]
    gdi32.BitBlt.argtypes = [HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, HDC, ctypes.c_int, ctypes.c_int,
                             wintypes.DWORD]
    gdi32.RoundRect.argtypes = [HDC] + [ctypes.c_int] * 6
    gdi32.Ellipse.argtypes = [HDC] + [ctypes.c_int] * 4
    gdi32.MoveToEx.argtypes = [HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    gdi32.LineTo.argtypes = [HDC, ctypes.c_int, ctypes.c_int]
    gdi32.Polyline.argtypes = [HDC, ctypes.POINTER(wintypes.POINT), ctypes.c_int]
    gdi32.SetBkMode.argtypes = [HDC, ctypes.c_int]
    gdi32.SetTextColor.argtypes = [HDC, CR]
    gdi32.SetBkColor.argtypes = [HDC, CR]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [HDC, HB, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    # 裁剪区域：SaveDC/RestoreDC + IntersectClipRect
    gdi32.SaveDC.restype = ctypes.c_int
    gdi32.SaveDC.argtypes = [HDC]
    gdi32.RestoreDC.restype = ctypes.c_int
    gdi32.RestoreDC.argtypes = [HDC, ctypes.c_int]
    gdi32.IntersectClipRect.restype = ctypes.c_int
    gdi32.IntersectClipRect.argtypes = [HDC] + [ctypes.c_int] * 4

    # ---- kernel32 / shell32
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]


class Font:
    """GDI 字体句柄。"""

    def __init__(self, height: int, weight: int = 400, name: str = "Microsoft YaHei UI",
                 quality: int = CLEARTYPE_QUALITY):
        self.height = height
        self.weight = weight
        self.name = name
        self.quality = quality
        self._h = None
        self._scale = 0.0

    def create(self, scale: float = 1.0):
        # 同一个 Font 对象会被画布和原生控件共用，而句柄只能有一个「真实大小」：
        # 谁最后建谁说了算。所以这里记住建的时候用的缩放，
        # 缩放没变就直接复用，变了才重建（窗口挪到不同 DPI 的显示器时会走到这里）。
        # 之前原生 EDIT 偷偷用默认 1.0 重建过一次，
        # 结果控件里的字和界面差一号大 —— 这就是「比例不对」的一个来源。
        if self._h is not None and abs(self._scale - scale) < 0.01:
            return self._h
        if self._h is not None:
            gdi32.DeleteObject(self._h)
        h = gdi32.CreateFontW(
            -int(abs(self.height) * scale), 0, 0, 0, self.weight, 0, 0, 0,
            1,  # DEFAULT_CHARSET
            0,  # OUT_DEFAULT_PRECIS
            0,  # CLIP_DEFAULT_PRECIS
            self.quality, 0, self.name)
        self._h = h
        self._scale = scale
        return h

    def metrics(self, scale: float = 1.0) -> tuple[int, int]:
        """返回 (字高, 行外距)，单位是**物理像素**。

        原生单行 EDIT 画文字是从客户区顶部往下画的，
        给它多高就决定了字浮在哪儿 —— 所以要先量出字到底多高。
        """
        h = self.create(scale)
        dc = gdi32.CreateCompatibleDC(None)
        old = gdi32.SelectObject(dc, h)
        tm = TEXTMETRIC()
        gdi32.GetTextMetricsW(dc, ctypes.byref(tm))
        gdi32.SelectObject(dc, old)
        gdi32.DeleteDC(dc)
        return tm.tmHeight, tm.tmExternalLeading

    def destroy(self):
        if self._h:
            gdi32.DeleteObject(self._h)
            self._h = None
            self._scale = 0.0


class Canvas:
    """双缓冲 GDI 画布，所有坐标按设计像素传入，内部乘以 scale。"""

    def __init__(self, hdc, width: int, height: int, scale: float = 1.0):
        self.scale = scale
        self.w = width
        self.h = height
        self.hdc = hdc
        self.mem_dc = gdi32.CreateCompatibleDC(hdc)
        self.bitmap = gdi32.CreateCompatibleBitmap(hdc, int(width * scale),
                                                    int(height * scale))
        gdi32.SelectObject(self.mem_dc, self.bitmap)
        self._brush = None
        self._pen = None

    def close(self):
        if self.bitmap:
            gdi32.DeleteObject(self.bitmap)
        if self.mem_dc:
            gdi32.DeleteDC(self.mem_dc)
        self.bitmap = None
        self.mem_dc = None

    # ---------------------------------------------------------- 基础
    def s(self, v: float) -> int:
        """设计像素 -> 实际像素"""
        return int(round(v * self.scale))

    def fill(self, color: str):
        brush = gdi32.CreateSolidBrush(rgb(color))
        rect = wintypes.RECT(0, 0, self.s(self.w), self.s(self.h))
        user32.FillRect(self.mem_dc, ctypes.byref(rect), brush)
        gdi32.DeleteObject(brush)

    def fill_rect(self, x, y, w, h, color: str):
        brush = gdi32.CreateSolidBrush(rgb(color))
        rect = wintypes.RECT(self.s(x), self.s(y), self.s(x + w), self.s(y + h))
        user32.FillRect(self.mem_dc, ctypes.byref(rect), brush)
        gdi32.DeleteObject(brush)

    def round_rect(self, x, y, w, h, radius, fill: str | None = None,
                   stroke: str | None = None, stroke_w: float = 1.0):
        """圆角矩形：填充 + 可选 1px 描边。

        坑：描边必须用 **CreatePen**。早先这里图省事用 CreateSolidBrush 当画笔，
        SelectObject 会按对象类型把它塞进「填充画刷」槽，把真正的填充色顶掉 ——
        表现就是整块被描边色填满（卡片像被染了一层色、药丸控件的边变成实心）。
        """
        brush = gdi32.CreateSolidBrush(rgb(fill)) if fill else gdi32.GetStockObject(5)
        pen = (gdi32.CreatePen(0, max(1, int(stroke_w * self.scale)), rgb(stroke))
               if stroke else gdi32.GetStockObject(8))
        old_b = gdi32.SelectObject(self.mem_dc, brush)
        old_p = gdi32.SelectObject(self.mem_dc, pen)
        gdi32.RoundRect(self.mem_dc, self.s(x), self.s(y), self.s(x + w),
                        self.s(y + h), self.s(radius * 2), self.s(radius * 2))
        gdi32.SelectObject(self.mem_dc, old_b)
        gdi32.SelectObject(self.mem_dc, old_p)
        if fill:
            gdi32.DeleteObject(brush)
        if stroke:
            gdi32.DeleteObject(pen)

    def ellipse(self, x, y, w, h, fill: str):
        brush = gdi32.CreateSolidBrush(rgb(fill))
        old = gdi32.SelectObject(self.mem_dc, brush)
        gdi32.Ellipse(self.mem_dc, self.s(x), self.s(y), self.s(x + w), self.s(y + h))
        gdi32.SelectObject(self.mem_dc, old)
        gdi32.DeleteObject(brush)

    def line(self, x1, y1, x2, y2, color: str, width: float = 1.0):
        pen = gdi32.CreatePen(0, max(1, int(width * self.scale)), rgb(color))
        old = gdi32.SelectObject(self.mem_dc, pen)
        gdi32.MoveToEx(self.mem_dc, self.s(x1), self.s(y1), None)
        gdi32.LineTo(self.mem_dc, self.s(x2), self.s(y2))
        gdi32.SelectObject(self.mem_dc, old)
        gdi32.DeleteObject(pen)

    def polyline(self, points, color: str, width: float = 1.0):
        """画连续折线（圆弧仪表 / 趋势线都走这个）。"""
        pts = list(points)
        if len(pts) < 2:
            return
        pen = gdi32.CreatePen(0, max(1, int(width * self.scale)), rgb(color))
        old = gdi32.SelectObject(self.mem_dc, pen)
        arr = (wintypes.POINT * len(pts))()
        for i, (px, py) in enumerate(pts):
            arr[i] = wintypes.POINT(self.s(px), self.s(py))
        gdi32.Polyline(self.mem_dc, arr, len(pts))
        gdi32.SelectObject(self.mem_dc, old)
        gdi32.DeleteObject(pen)

    # ---------------------------------------------------------- 文字
    def text(self, x, y, w, h, s: str, font: Font, color: str,
             align: int = DT_LEFT | DT_VCENTER | DT_SINGLELINE,
             clip: bool = True):
        if font._h is None:
            font.create(self.scale)
        gdi32.SelectObject(self.mem_dc, font._h)
        gdi32.SetBkMode(self.mem_dc, TRANSPARENT)
        gdi32.SetTextColor(self.mem_dc, rgb(color))
        rect = wintypes.RECT(self.s(x), self.s(y), self.s(x + w), self.s(y + h))
        flags = align | DT_NOPREFIX
        if clip:
            flags |= DT_END_ELLIPSIS
        user32.DrawTextW(self.mem_dc, s, -1, ctypes.byref(rect), flags)

    def measure(self, s: str, font: Font) -> tuple[int, int]:
        """量文字的宽高。

        返回的是**设计像素**（跟 text() 的坐标系一致）——
        DrawTextW 算出来的是物理像素，150% 的屏上直接返回会大 1.5 倍，
        拿来排版就会整体散架。
        """
        if font._h is None:
            font.create(self.scale)
        gdi32.SelectObject(self.mem_dc, font._h)
        gdi32.SetBkMode(self.mem_dc, TRANSPARENT)
        rect = wintypes.RECT(0, 0, 0, 0)
        user32.DrawTextW(self.mem_dc, s, -1, ctypes.byref(rect),
                          DT_CALCRECT | DT_SINGLELINE | DT_NOPREFIX)
        return (int((rect.right - rect.left) / self.scale),
                int((rect.bottom - rect.top) / self.scale))

    # ---------------------------------------------------------- 输出
    def blit(self, hdc):
        gdi32.BitBlt(hdc, 0, 0, self.s(self.w), self.s(self.h),
                     self.mem_dc, 0, 0, 0x00CC0020)  # SRCCOPY

    # ---------------------------------------------------------- 裁剪
    def push_clip(self, x, y, w, h):
        """限制后续绘制区域，返回一个 token，交给 pop_clip 恢复。"""
        dc = self.mem_dc
        token = gdi32.SaveDC(dc)
        gdi32.IntersectClipRect(dc, self.s(x), self.s(y),
                                self.s(x + w), self.s(y + h))
        return token

    def pop_clip(self, token):
        gdi32.RestoreDC(self.mem_dc, token)


def _trace_cursor(cur: int, extra: str = "") -> None:
    """记录 WM_SETCURSOR 算出来的光标 ID（调试用）。

    锁屏状态下 GetCursor() 读到的是 Winlogon 桌面的光标，外部验不了，
    只能让窗口自己报。
    """
    try:
        with open(_trace_path(), "a", encoding="utf-8") as f:
            f.write(f"    -> WM_SETCURSOR cursor_id={cur} {extra}\n")
    except Exception:  # noqa: BLE001
        pass


class Edit:
    """原生编辑框（父窗口的子控件）。

    为什么用系统的 EDIT 而不是自绘一个输入框：
    输入法（中文/候选词）、粘贴、剪切、撤销重做、全选、双击选词、
    光标闪烁、横向滚动——这些自己实现一遍坑多且不值当，
    系统控件全都现成，而且深色主题只需要处理 WM_CTLCOLOREDIT。

    注意：单行 EDIT 的高度**不会**被系统按字体改掉（实测传多少就是多少），
    而它画文字是从客户区顶部往下画的 —— 所以高度得自己算对，
    不然字会浮在框顶，下面空一大块。
    """

    def __init__(self, parent: int, x: int, y: int, w: int, h: int,
                 text: str = "", password: bool = False,
                 multiline: bool = False, font=None,
                 control_id: int | None = None, scale: float = 1.0):
        style = WS_CHILD | WS_VISIBLE | WS_TABSTOP
        if multiline:
            style |= ES_MULTILINE | ES_AUTOVSCROLL | ES_WANTRETURN
        else:
            style |= ES_AUTOHSCROLL
        if password:
            style |= ES_PASSWORD
        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd = user32.CreateWindowExW(
            0, "EDIT", text, style, int(x), int(y), int(w), int(h),
            parent, control_id, hinst, None)
        if not self.hwnd:
            raise OSError(f"CreateWindowExW(EDIT) 失败: {ctypes.get_last_error()}")
        self.font = font
        if font is not None:
            # 关键：scale 必须跟画布一致。之前这里用的是默认 1.0，
            # 控件里的字会比界面上其它字小一号（150% 的屏上就是 10px vs 15px）。
            user32.SendMessageW(self.hwnd, WM_SETFONT, font.create(scale), 1)
        self.set_rect(x, y, w, h)
        # 左右各留 6px 内边距：原生 EDIT 默认文字紧贴边框，看起来像被裁掉
        user32.SendMessageW(self.hwnd, EM_SETMARGINS,
                            EC_LEFTMARGIN | EC_RIGHTMARGIN, 6 | (6 << 16))

    def client_size(self) -> tuple[int, int]:
        """客户区尺寸（物理像素）。"""
        if not self.hwnd:
            return (0, 0)
        rc = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rc))
        return (rc.right - rc.left, rc.bottom - rc.top)

    # ---------------------------------------------------------- 内容
    def get_text(self) -> str:
        if not self.hwnd:
            return ""
        n = user32.GetWindowTextLengthW(self.hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(self.hwnd, buf, n + 1)
        return buf.value

    def set_text(self, text: str) -> None:
        if self.hwnd:
            user32.SetWindowTextW(self.hwnd, text or "")

    def select_all(self) -> None:
        if self.hwnd:
            user32.SendMessageW(self.hwnd, EM_SETSEL, 0, -1)

    # ---------------------------------------------------------- 外观
    def set_rect(self, x: int, y: int, w: int, h: int) -> None:
        if self.hwnd:
            user32.SetWindowPos(self.hwnd, None, int(x), int(y), int(w), int(h),
                                SWP_NOZORDER | SWP_NOACTIVATE)

    def set_password_char(self, ch: str) -> None:
        """ES_PASSWORD 用系统默认的 •；传空串则显示明文。"""
        if self.hwnd:
            user32.SendMessageW(self.hwnd, EM_SETPASSWORDCHAR,
                                ord(ch) if ch else 0, 0)

    def show(self, visible: bool = True) -> None:
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_SHOW if visible else SW_HIDE)

    def focus(self) -> None:
        if self.hwnd:
            user32.SetFocus(self.hwnd)

    def destroy(self) -> None:
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


class Window:
    """一个顶层窗口：负责创建、消息循环、绘制回调。"""

    # 编辑框配色（子类可覆盖）
    edit_bg_color = "#1C2739"
    edit_text_color = "#ECF1FA"

    def __init__(self, title: str, width: int, height: int,
                 class_name: str = "TokenBoardWindow",
                 x: int = CW_USEDEFAULT, y: int = CW_USEDEFAULT,
                 style: int = WS_FIXED, ex_style: int = WS_EX_APPWINDOW):
        self.scale = enable_dpi_awareness()
        self.title = title
        self.width = width
        self.height = height
        self.class_name = class_name
        self.x = x
        self.y = y
        self.style = style
        self.ex_style = ex_style
        self._bg_color = "#FFFFFF"    # 背景色，绘制前先铺一遍
        self.hwnd = None
        self.visible = False
        self._canvas: Canvas | None = None
        self._proc = None
        self._mouse_x = -1             # 当前鼠标位置（设计像素），用于悬停高亮
        self._mouse_y = -1
        # 可缩放窗口：边缘留一条缩放热区，最小尺寸（设计像素）
        self.resize_border = 5
        self.min_width = 620
        self.min_height = 420
        # 设计尺寸（不可变）：最小尺寸的**上限**。
        # 桌面小框设计成 240x80，比基类下限 620x420 小得多；
        # 最小尺寸一旦超过设计尺寸，它一创建就被撑成一大块底板。
        self.design_width = width
        self.design_height = height
        self._pending_outer = (0, 0)   # WM_WINDOWPOSCHANGING 带来的新窗口尺寸
        # 子控件（编辑框）
        self._edit_brush = None
        self._edits: list[Edit] = []
        # Explorer 重启后通知区域会被清空，这个广播消息用来触发重新注册
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

    # ------------------------------------------------------------------
    def create(self):
        hinst = kernel32.GetModuleHandleW(None)

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                return self._handle(hwnd, msg, wparam, lparam)
            except Exception:  # noqa: BLE001
                # 窗口版程序没有控制台，print 到 stderr 等于丢掉了 ——
                # 写进日志文件，否则异常会静默地把界面画崩。
                import traceback
                try:
                    from ..config import LOG_PATH
                    with open(LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(f"[wndproc] msg=0x{msg:04X}\n"
                                f"{traceback.format_exc()}\n")
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc = WNDPROC(wndproc)

        wc = WNDCLASS()
        wc.style = CS_HREDRAW | CS_VREDRAW | CS_DBLCLKS
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
        wc.hbrBackground = 0
        wc.lpszClassName = self.class_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err not in (0, 1410):   # 1410 = 已注册
                raise OSError(f"RegisterClassW failed: {err}")

        # 自绘标题栏：WM_NCCALCSIZE 返回 0 后客户区 = 整个窗口，
        # 所以窗口尺寸直接用设计尺寸，不用再为系统标题栏预留高度。
        outer_w = int(self.width * self.scale)
        outer_h = int(self.height * self.scale)

        self.hwnd = user32.CreateWindowExW(
            self.ex_style, self.class_name, self.title,
            self.style,
            self.x, self.y,
            outer_w, outer_h,
            None, None, hinst, None)
        if not self.hwnd:
            raise OSError(f"CreateWindowExW failed: {ctypes.get_last_error()}")

        # 校验客户区尺寸：AdjustWindowRectEx 不做 DPI 换算，可能差几个像素
        cr = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(cr))
        want_w = int(self.width * self.scale)
        want_h = int(self.height * self.scale)
        _tlog(f"[create] want={want_w}x{want_h} client={cr.right}x{cr.bottom} "
              f"self={self.width}x{self.height} scale={self.scale}")
        if cr.right != want_w or cr.bottom != want_h:
            dw = want_w - cr.right
            dh = want_h - cr.bottom
            rw = wintypes.RECT(0, 0, 0, 0)
            user32.GetWindowRect(self.hwnd, ctypes.byref(rw))
            _tlog(f"[create] 修正窗口尺寸 +{dw}x+{dh} "
                  f"(窗口原为 {rw.right - rw.left}x{rw.bottom - rw.top})")
            user32.MoveWindow(self.hwnd, rw.left, rw.top,
                              rw.right - rw.left + dw, rw.bottom - rw.top + dh,
                              True)
            cr2 = wintypes.RECT()
            user32.GetClientRect(self.hwnd, ctypes.byref(cr2))
            _tlog(f"[create] 修正后 client={cr2.right}x{cr2.bottom}")
        self._enable_dark_titlebar()
        self._round_corners()
        return self.hwnd

    def _enable_dark_titlebar(self):
        """让 Windows 标题栏也跟着变深色（否则白标题栏配深色内容很割裂）。

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20（Win10 20H1+ / Win11），
        19 是旧版。失败就算了，不影响主界面。
        """
        try:
            dwmapi = ctypes.windll.dwmapi
        except Exception:  # noqa: BLE001
            return
        for attr in (20, 19):
            try:
                val = ctypes.c_int(1)
                hr = dwmapi.DwmSetWindowAttribute(
                    self.hwnd, ctypes.c_int(attr), ctypes.byref(val),
                    ctypes.sizeof(val))
                if hr == 0:
                    return
            except Exception:  # noqa: BLE001
                continue

    def _round_corners(self):
        """Win11 圆角窗口（DWMWA_WINDOW_CORNER_PREFERENCE = 33）。

        值 2 = DWMWCP_ROUND，值 1 = 小圆角，0 = 不圆角。
        老版本 Windows 不支持这个属性，调用失败就忽略。
        """
        try:
            dwmapi = ctypes.windll.dwmapi
            val = ctypes.c_int(2)
            dwmapi.DwmSetWindowAttribute(
                self.hwnd, ctypes.c_int(33), ctypes.byref(val),
                ctypes.sizeof(val))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    def _handle(self, hwnd, msg, wparam, lparam):
        if _TRACE:
            _trace(self, msg, wparam, lparam)
        if msg == WM_PAINT:
            self.on_paint()
            return 0
        if msg == WM_PRINTCLIENT:
            # 同进程内渲染到指定 DC（外部工具跨进程抓图请走 PrintWindow，
            # GDI 的 DC 是进程私有的，跨进程传过来会静默失败变成全黑图）。
            hdc = wintypes.HDC(int(wparam) & 0xFFFFFFFF)
            if not gdi32.GetDeviceCaps(hdc, 8):   # HORZRES==0 -> DC 无效
                return 1
            self._render_to(hdc)
            return 1
        if msg == WM_ERASEBKGND:
            return 1          # 自己画背景，别让系统擦
        if msg == WM_CLOSE:
            self.on_close()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        if msg == WM_TIMER:
            self.on_timer(wparam)
            return 0
        if msg == WM_EXITSIZEMOVE:
            # 拖动/缩放结束：小框要在这里记住新位置
            self.on_moved()
            return 0
        if msg == WM_LBUTTONDOWN:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self.on_click(x / self.scale, y / self.scale)
            return 0
        if msg == WM_LBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._mouse_x = x / self.scale
            self._mouse_y = y / self.scale
            self.on_click_up(self._mouse_x, self._mouse_y)
            return 0
        if msg == WM_RBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._mouse_x = x / self.scale
            self._mouse_y = y / self.scale
            self.on_right_click(self._mouse_x, self._mouse_y)
            return 0
        if msg == WM_CHAR:
            # 仅转发给窗口用于搜索输入；未聚焦时什么也不发生
            if self.on_char(chr(wparam)):
                return 0
        if msg == WM_MOUSEMOVE:
            # 滚轮消息只发给「有焦点的窗口」。面板是浮窗，用户常常是悬停着滚的，
            # 焦点还在别的程序上 —— 那就鼠标一进来先把焦点抢过来。
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._mouse_x = x / self.scale
            self._mouse_y = y / self.scale
            inside = 0 <= x < int(self.width * self.scale) and \
                0 <= y < int(self.height * self.scale)
            if inside and not getattr(self, "_mouse_in", False):
                self._mouse_in = True
                if user32.GetForegroundWindow() != self.hwnd:
                    user32.SetForegroundWindow(self.hwnd)
            elif not inside:
                self._mouse_in = False
            if inside:
                self._track_leave()
            self.on_mousemove(self._mouse_x, self._mouse_y)
            self.on_hover()
            return 0
        if msg == WM_MOUSELEAVE:
            # 鼠标移出窗口：没有这个事件的话，悬停高亮会一直卡住。
            self._mouse_in = False
            self._leave_tracked = False
            self.on_mouseleave()
            return 0
        if msg == WM_NCMOUSEMOVE:
            # 鼠标在**非客户区**上移动：窗口整块当拖动区时（桌面小框），
            # 鼠标消息走的是 NC 版本，WM_MOUSEMOVE 根本不来。
            # 不接这个消息，悬停高亮会一直卡在「鼠标不在上面」。
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            pt = wintypes.POINT(x, y)
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            self._mouse_x = pt.x / self.scale
            self._mouse_y = pt.y / self.scale
            _tlog(f"[NCMOUSEMOVE] screen=({x},{y}) client=({pt.x},{pt.y}) "
                  f"design=({self._mouse_x:.1f},{self._mouse_y:.1f})")
            self._track_leave_nc()
            self.on_mousemove(self._mouse_x, self._mouse_y)
            self.on_hover()
            return 0
        if msg == WM_NCMOUSELEAVE:
            self._leave_nc_tracked = False
            self.on_mouseleave()
            return 0
        if msg == WM_KEYDOWN:
            self.on_key(wparam)
            return 0
        if msg == WM_MOUSEWHEEL:
            # wparam 高 16 位是滚轮增量（一格 = 120），**是有符号的**：
            # 直接 >> 16 会把 -120 算成 65416，÷120 后变成 545，
            # 一下就滚到最底，看起来就像"滑不动"。
            raw = (wparam >> 16) & 0xFFFF
            delta = ctypes.c_short(raw).value
            if delta:
                self.on_mouse_wheel(-(delta // 120) if delta > 0 else (-delta) // 120)
            return 0
        if msg == WM_SETCURSOR:
            if self.on_set_cursor():
                return 1
            # 鼠标停在边缘/角上时换成缩放光标 —— 默认箭头会让人以为拖不动
            cur = self._resize_cursor()
            if _TRACE:
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                scr = (pt.x, pt.y)
                user32.ScreenToClient(self.hwnd, ctypes.byref(pt))
                _trace_cursor(cur, f"screen={scr} client=({pt.x},{pt.y}) "
                                   f"logical=({pt.x / self.scale:.1f},"
                                   f"{pt.y / self.scale:.1f})")
            if cur:
                user32.SetCursor(user32.LoadCursorW(None, ctypes.c_void_p(cur)))
                return 1
            return 0
        if msg == WM_COMMAND:
            hi = (wparam >> 16) & 0xFFFF
            lo = wparam & 0xFFFF
            if hi:
                # 来自子控件（编辑框的 EN_CHANGE 等），必须返回 0，
                # 否则系统会「哔」一声。
                self.on_child_command(lo, hi, lparam)
                return 0
            self.on_command(lo)
            return 0
        if msg == WM_TRAY:
            # 注意：托盘回调用的是 WM_APP+1(0x8001)，不是 WM_APP(0x8000)。
            # 之前写成 `msg == WM_APP` 永远匹配不上，点图标毫无反应。
            self.on_tray(wparam, lparam)
            return 0
        if msg == WM_GETMINMAXINFO:
            mmi = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
            # 同 WM_WINDOWPOSCHANGING：最小跟踪尺寸不能超过设计尺寸，
            # 否则系统在拖动时会把小框「撑」到基类下限。
            mmi.ptMinTrackSize.x = int(
                min(self.min_width, self.design_width) * self.scale)
            mmi.ptMinTrackSize.y = int(
                min(self.min_height, self.design_height) * self.scale)
            return 0
        if msg == WM_SIZE:
            # 新尺寸在 **lParam** 里（LOWORD=宽, HIWORD=高），wParam 实测是 0。
            # （网上不少地方写的是 wParam，实测不成立，别照抄。）
            w = int(lparam & 0xFFFF)
            h = int((lparam >> 16) & 0xFFFF)
            if not w or not h:
                cr = wintypes.RECT()
                user32.GetClientRect(hwnd, ctypes.byref(cr))
                w, h = cr.right, cr.bottom
            if w and h:
                _tlog(f"[WM_SIZE] 新尺寸 {w}x{h} 物理像素")
                self.on_size(w, h)
            return 0
        if msg == WM_NCCALCSIZE:
            if not wparam:
                _tlog("[NCCALCSIZE] wparam=0 -> 走默认处理（客户区按系统边框内缩）")
                return 0
            # 去掉系统标题栏/边框：客户区铺满整个窗口。
            #
            # 坑（踩过，务必保留）：这里写 rgrc[0] 必须写**屏幕坐标**。
            # 写窗口坐标 (0,0,w,h) 的话，窗口不在屏幕原点时客户区会被钉在
            # 屏幕 (0,0)，界面左上角被裁掉一块（配置窗口建在 200,120 时，
            # 标题栏和左侧 provider 列表整个不见了）。
            #
            # 客户区大小也不能用 GetWindowRect 取 —— 缩放时系统还没更新窗口
            # 矩形，拿到的还是旧尺寸，客户区会卡在旧大小；新尺寸在
            # WM_WINDOWPOSCHANGING 里已经给出来了（_pending_outer）。
            params = ctypes.cast(lparam, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
            w, h = self._pending_outer
            src = "pending"
            if not w or not h:
                wr = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(wr))
                w = wr.right - wr.left
                h = wr.bottom - wr.top
                src = "GetWindowRect"
            # 窗口在屏幕上的原点：WINDOWPOS 里一定有（x/y 是屏幕坐标）
            ox, oy = 0, 0
            if params.ppos:
                pos = ctypes.cast(params.ppos, ctypes.POINTER(WINDOWPOS)).contents
                ox, oy = pos.x, pos.y
            else:
                wr = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(wr))
                ox, oy = wr.left, wr.top
            rc = ctypes.cast(lparam, ctypes.POINTER(wintypes.RECT)).contents
            rc.left = ox
            rc.top = oy
            rc.right = ox + w
            rc.bottom = oy + h
            _tlog(f"[NCCALCSIZE] 客户区 {w}x{h} 屏幕原点=({ox},{oy}) 来源={src}")
            return True
        if msg == WM_WINDOWPOSCHANGING:
            # 记下新的窗口尺寸（WM_NCCALCSIZE 马上就会用到）
            pos = ctypes.cast(lparam, ctypes.POINTER(WINDOWPOS)).contents
            # SWP_NOSIZE = 本次只是显示/移动，尺寸没变，此时 **cx/cy 是 0**。
            # 早前在这里无条件做最小尺寸钳制，把 0 钳成了最小值 930x630，
            # 结果窗口还是 1050x645、客户区却被改成 930x630：
            # 右边 120px、下边 15px 成了没人画的非客户区，
            # 缩放热区也跟着错位（看起来就是「边缘拖不动 / 缩放不对」）。
            if pos.flags & SWP_NOSIZE:
                _tlog("[WINDOWPOSCHANGING] SWP_NOSIZE（尺寸未变），忽略 cx/cy")
                return 0
            # 拖动（模态移动）时系统**不带** SWP_NOSIZE，但 cx/cy 就是当前尺寸。
            # 早前在这里无条件做最小尺寸钳制：360x120 的小框被钳成 930x630，
            # 用户拖一下小框就变成一大块深色底板（卡片缩在左上角）。
            # 尺寸没变 = 纯移动，一律不碰尺寸。
            cur = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(cur))
            cur_w, cur_h = cur.right - cur.left, cur.bottom - cur.top
            if cur_w and cur_h and pos.cx == cur_w and pos.cy == cur_h:
                self._pending_outer = (pos.cx, pos.cy)
                _tlog(f"[WINDOWPOSCHANGING] 纯移动 {pos.cx}x{pos.cy}，尺寸不动")
                return 0
            # 自己钳一次最小尺寸：WM_GETMINMAXINFO 只在「用户拖动」时被查询，
            # 程序化 MoveWindow / 键盘缩放不查它，靠这里兜底。
            # 最小尺寸不能超过窗口自己的设计尺寸 —— 否则设计成 240x80 的
            # 小框，一创建就被撑到基类下限 620x420。
            min_w = int(min(self.min_width, self.design_width) * self.scale)
            min_h = int(min(self.min_height, self.design_height) * self.scale)
            if pos.cx < min_w:
                pos.cx = min_w
            if pos.cy < min_h:
                pos.cy = min_h
            self._pending_outer = (pos.cx, pos.cy)
            _tlog(f"[WINDOWPOSCHANGING] pos={pos.cx}x{pos.cy} 最小={min_w}x{min_h}")
            return 0
        if msg == WM_NCPAINT:
            # 非客户区由我们自己画，别让系统再刷一遍旧标题栏
            return 0
        if msg == WM_CTLCOLOREDIT:
            # 深色主题下的编辑框：系统默认是白底黑字，跟面板格格不入
            hdc = wintypes.HDC(int(wparam) & 0xFFFFFFFF)
            gdi32.SetTextColor(hdc, rgb(self.edit_text_color))
            gdi32.SetBkColor(hdc, rgb(self.edit_bg_color))
            if self._edit_brush is None:
                self._edit_brush = gdi32.CreateSolidBrush(rgb(self.edit_bg_color))
            return self._edit_brush
        if msg == WM_NCACTIVATE:
            return 1
        if msg == WM_SETTINGCHANGE:
            # 系统主题/强调色变了（「跟随系统」时要重新取色）。
            # lParam 指向变化项的名称，这里不区分，统一通知子类自己判断。
            self.on_setting_change()
            return 0
        if msg == WM_NCHITTEST:
            # 屏幕坐标 -> 客户区坐标
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            pt = wintypes.POINT(x, y)
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            return self.on_nc_hit_test(pt.x / self.scale, pt.y / self.scale)
        if msg == self._taskbar_created:
            # Explorer 重启后会把所有通知区域图标清掉，必须重新注册，
            # 否则托盘里的图标会凭空消失。
            self.on_taskbar_created()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ------------------------------------------------------------------
    def create_edit(self, x: int, y: int, w: int, h: int, text: str = "",
                    password: bool = False, multiline: bool = False,
                    font=None) -> Edit:
        """在窗口里放一个原生编辑框。"""
        e = Edit(self.hwnd, x, y, w, h, text=text, password=password,
                 multiline=multiline, font=font, scale=self.scale)
        self._edits.append(e)
        return e

    def show(self):
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.UpdateWindow(self.hwnd)
        # 从「隐藏启动」的父进程（计划任务 / 隐匿启动的终端）拉起时，
        # 第一次 ShowWindow 会被 STARTUPINFO 里的 SW_HIDE 顶掉 —— 窗口明明创建了却看不见。
        # 再调一次就按显式参数生效了。
        if not user32.IsWindowVisible(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_SHOWNORMAL)
            user32.UpdateWindow(self.hwnd)
        self.visible = True
        if _TRACE:
            _tlog(f"[show] 客户区原点={self.client_origin()}")

    def client_origin(self) -> tuple[int, int]:
        """客户区左上角的屏幕坐标（诊断用）。"""
        if not self.hwnd:
            return (0, 0)
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(pt))
        return (pt.x, pt.y)

    def hide(self):
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self.visible = False

    def bring_to_front(self):
        user32.ShowWindow(self.hwnd, SW_RESTORE)
        user32.SetForegroundWindow(self.hwnd)
        self.visible = True
        if _TRACE:
            _tlog(f"[bring_to_front] 客户区原点={self.client_origin()}")

    # ---- 位置 / 层级 -------------------------------------------------
    def move_to(self, x: int, y: int):
        """移动窗口（保持尺寸）。"""
        if not self.hwnd:
            return
        user32.SetWindowPos(self.hwnd, None, int(x), int(y), 0, 0,
                            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)

    def get_pos(self) -> tuple[int, int]:
        """窗口在屏幕上的左上角坐标（物理像素）。"""
        if not self.hwnd:
            return (0, 0)
        r = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r.left, r.top

    def set_topmost(self, on: bool = True):
        if not self.hwnd:
            return
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
                            0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def set_layered_alpha(self, alpha: int):
        """整窗透明度（0 完全看不见，255 完全不透明）。

        窗口必须带 WS_EX_LAYERED 才有效果。
        注意这是**整体**alpha：底板和文字会一起变淡 ——
        想要「底板半透明、文字实心」得用 UpdateLayeredWindow 的逐像素 alpha。
        """
        if not self.hwnd:
            return
        user32.SetLayeredWindowAttributes(self.hwnd, 0,
                                          max(0, min(255, int(alpha))), LWA_ALPHA)

    def invalidate(self):
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, False)

    def set_timer(self, interval_ms: int, tid: int = 1):
        user32.SetTimer(self.hwnd, tid, interval_ms, None)

    def kill_timer(self, tid: int = 1):
        user32.KillTimer(self.hwnd, tid)

    def _track_leave(self):
        """申请一次 WM_MOUSELEAVE（鼠标移出本窗口时通知）。

        Windows 只在鼠标**进入**窗口时发消息，移出去默认不发 ——
        桌面小框的悬停高亮就会一直卡在「悬停中」。
        """
        if getattr(self, "_leave_tracked", False):
            return
        tm = TRACKMOUSEEVENT()
        tm.cbSize = ctypes.sizeof(TRACKMOUSEEVENT)
        tm.dwFlags = TME_LEAVE
        tm.hwndTrack = self.hwnd
        tm.dwHoverTime = 0
        self._leave_tracked = True
        user32.TrackMouseEvent(ctypes.byref(tm))

    def _track_leave_nc(self):
        """申请一次 WM_NCMOUSELEAVE（鼠标移出**非客户区**时通知）。

        窗口整块当拖动区时（小框），鼠标消息走的都是 NC 版本，
        WM_MOUSELEAVE 不会来 —— 悬停高亮就没法知道鼠标已经走了。
        """
        if getattr(self, "_leave_nc_tracked", False):
            return
        tm = TRACKMOUSEEVENT()
        tm.cbSize = ctypes.sizeof(TRACKMOUSEEVENT)
        tm.dwFlags = TME_LEAVE | TME_NONCLIENT
        tm.hwndTrack = self.hwnd
        tm.dwHoverTime = 0
        self._leave_nc_tracked = True
        user32.TrackMouseEvent(ctypes.byref(tm))

    def run(self):
        msg = MSG()
        while True:
            got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def destroy(self):
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    # ------------------------------------------------------------------
    # 子类可覆盖
    def on_paint(self):
        hdc = user32.GetDC(self.hwnd)
        try:
            if self._canvas is None:
                self._canvas = Canvas(hdc, self.width, self.height, self.scale)
            ps = PAINTSTRUCT()
            user32.BeginPaint(self.hwnd, ctypes.byref(ps))
            self._render(ps.hdc)
            user32.EndPaint(self.hwnd, ctypes.byref(ps))
        finally:
            user32.ReleaseDC(self.hwnd, hdc)

    def _render(self, hdc) -> None:
        """把界面画到指定的 DC（WM_PAINT 用常驻画布，屏幕刷新用这个）。"""
        if self._canvas is None:
            self._canvas = Canvas(hdc, self.width, self.height, self.scale)
        self._canvas.fill(self._bg_color)
        self.draw(self._canvas)
        self._canvas.blit(hdc)

    def _render_to(self, hdc) -> None:
        """渲染到任意 DC（截图用）。

        这里**不复用**屏幕上的常驻画布：那块画布的内存 DC 是照着屏幕 DC 建的，
        往内存 DC 上 blit 会跨设备失败，结果就是一张全黑的图。
        现画一张跟目标 DC 兼容的临时画布，保证结果可复现。
        """
        canvas = Canvas(hdc, self.width, self.height, self.scale)
        try:
            canvas.fill(self._bg_color)
            self.draw(canvas)
            canvas.blit(hdc)
        finally:
            canvas.close()

    def draw(self, canvas: Canvas):
        pass

    def on_right_click(self, x: float, y: float):
        """默认忽略。子类覆盖打开右键菜单。"""

    def on_char(self, ch: str) -> bool:
        """返回 True 表示字符已被消费（搜索框）。默认不消费。"""
        return False

    def on_click(self, x: float, y: float):
        pass

    def on_click_up(self, x: float = 0.0, y: float = 0.0):
        pass

    def on_hover(self):
        pass

    def on_mousemove(self, x: float, y: float):
        """鼠标在窗口内移动（设计像素坐标）。"""
        pass

    def on_mouseleave(self):
        """鼠标移出窗口。"""
        pass

    def on_mouse_wheel(self, delta: int):
        pass

    def on_key(self, key: int):
        pass

    def on_timer(self, tid: int):
        pass

    def on_close(self):
        self.destroy()

    def on_command(self, cmd: int):
        pass

    def on_child_command(self, ctrl_id: int, notify: int, lparam: int):
        """子控件通知（编辑框 EN_CHANGE 等）。子类可覆盖。"""
        pass

    def on_tray(self, wparam: int, lparam: int):
        pass

    def on_taskbar_created(self):
        """Explorer 重启后重新往通知区域放回图标。"""
        pass

    def on_setting_change(self):
        """系统设置变化（主题 / 强调色 / DPI 等）。子类按需覆盖。"""

    def on_moved(self):
        """窗口被拖动/缩放结束。"""
        pass

    def on_set_cursor(self) -> bool:
        return False

    def _resize_cursor(self) -> int:
        """鼠标停在可缩放的边缘/角上时该用哪种光标，0 = 不用改。

        直接复用 on_nc_hit_test 的判定，两者永远一致 ——
        否则会出现「光标是缩放箭头、但那里其实拖不动」的错觉。
        """
        if not self.hwnd:
            return 0
        pt = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return 0
        if not user32.ScreenToClient(self.hwnd, ctypes.byref(pt)):
            return 0
        ht = self.on_nc_hit_test(pt.x / self.scale, pt.y / self.scale)
        return {
            HTLEFT: IDC_SIZEWE, HTRIGHT: IDC_SIZEWE,
            HTTOP: IDC_SIZENS, HTBOTTOM: IDC_SIZENS,
            HTTOPLEFT: IDC_SIZENWSE, HTBOTTOMRIGHT: IDC_SIZENWSE,
            HTTOPRIGHT: IDC_SIZENESW, HTBOTTOMLEFT: IDC_SIZENESW,
            HTCAPTION: IDC_SIZEALL,          # 标题栏：四向移动光标
        }.get(ht, 0)

    def on_nc_hit_test(self, x: float, y: float) -> int:
        """非客户区命中测试。

        返回 HTCAPTION 的区域由系统接管（可以拖动窗口），
        返回 HTCLIENT 的区域按普通客户区处理（能收到鼠标消息），
        返回 HTxxx（TOP/LEFT/…）的区域是缩放热区。
        """
        b = self.resize_border
        w, h = self.width, self.height
        left, right = x <= b, x >= w - b
        top, bottom = y <= b, y >= h - b
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return HTCLIENT

    def on_size(self, w: int, h: int):
        """窗口尺寸变了（w/h 是物理像素）。

        画布是按创建时的尺寸分配的，必须重建，否则只会画出一角。
        """
        self.width = w / self.scale
        self.height = h / self.scale
        if self._canvas is not None:
            self._canvas.close()
            self._canvas = None
        self.on_resize()
        self.invalidate()

    def on_resize(self):
        """尺寸变化后的钩子（子类重写，用来重排布局）。"""
        pass


# 必须在所有结构体定义完之后再声明原型
_setup_prototypes()
