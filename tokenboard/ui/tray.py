"""原生系统托盘（Shell_NotifyIcon），不依赖 pystray / Pillow。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from ..icon import make_icon_bits
from .win32 import (ICONINFO, NIF_ICON, NIF_MESSAGE, NIF_TIP, NIM_ADD,
                    NIM_DELETE, NIM_MODIFY, NIM_SETVERSION,
                    NOTIFYICON_VERSION_4, TPM_RETURNCMD, TPM_RIGHTBUTTON,
                    WM_TRAY, user32, shell32, gdi32)

WM_CONTEXTMENU_ID = 1001
WM_SHOW_ID = 1002
WM_REFRESH_ID = 1003
WM_QUIT_ID = 1004
WM_MINI_ID = 1005      # 显示 / 隐藏桌面小框
WM_SYNC_ID = 1006      # 立即同步（WebDAV）
WM_SETTINGS_ID = 1007  # 打开同步设置
WM_THEME_AUTO = 1010   # 外观：跟随系统
WM_THEME_LIGHT = 1011  # 外观：浅色
WM_THEME_DARK = 1012   # 外观：深色
MF_POPUP = 0x00000010


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def _alpha_mask_bits(w: int, h: int, bits: bytes) -> bytes:
    """按 alpha 通道生成 1bpp 的 AND 掩码（DDB 格式，自下而上）。

    AND 掩码里 1 = 画图标像素，0 = 保留背景。
    32bpp 图标的 alpha 决定透明度，所以掩码要按 alpha 的形状来：
    全 0 会让图标整个画不出来，全 1 又会把圆角外的透明区也涂上。
    """
    stride = ((w + 31) // 32) * 4      # 1bpp 每行按 4 字节对齐
    mask = bytearray(stride * h)
    for r in range(h):                  # bits 是自下而上的，第 0 行是最底行
        base = r * w * 4
        row = r * stride
        for x in range(w):
            if bits[base + x * 4 + 3] > 0:
                mask[row + (x >> 3)] |= 1 << (x & 7)
    return bytes(mask)


def _make_hicon(size: int = 32):
    """用 DIB 直接造一个图标句柄。"""
    w, h, bits = make_icon_bits(size)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h          # 负数 = 自上而下
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0      # BI_RGB

    ptr = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(None, ctypes.byref(bi), 0, ctypes.byref(ptr),
                                 None, 0)
    if not hbm:
        return None
    # GDI 句柄只有低 32 位有效，但 64 位下 API 把返回值放在 RAX 里，
    # 高 32 位是未初始化垃圾 —— ctypes 会照单全收，句柄变成
    # 0xFFFFFFFFxxxxxxxx，后面 CreateIconIndirect 直接失败（拿到 NULL 图标，
    # Shell_NotifyIcon 也就注册不上了）。这里必须自己掩掉高位。
    hbm &= 0xFFFFFFFF
    ctypes.memmove(ptr, bytes(bits), len(bits))

    # 32bpp 的 DIB 不能直接当 hbmColor：CreateIconIndirect 规定 hbmMask
    # 为 NULL 时 hbmColor 必须是设备相关位图(DDB)，传 DIB 会直接失败。
    # 所以补一张 1bpp 的 AND 掩码，形状取自 alpha 通道。
    mask_bytes = _alpha_mask_bits(w, h, bytes(bits))
    mask = gdi32.CreateBitmap(w, h, 1, 1, mask_bytes)
    if not mask:
        gdi32.DeleteObject(hbm)
        return None
    mask &= 0xFFFFFFFF

    info = ICONINFO()
    info.fIcon = True
    info.hbmMask = mask
    info.hbmColor = hbm
    hicon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(mask)
    gdi32.DeleteObject(hbm)
    return hicon


class Tray:
    """把图标挂到系统托盘；右键出菜单，左键切换面板显示。"""

    def __init__(self, window, on_show, on_refresh, on_quit,
                 on_toggle_mini=None, on_sync=None, on_settings=None,
                 on_theme=None, theme_pref="auto"):
        self.window = window
        self.on_show = on_show
        self.on_refresh = on_refresh
        self.on_quit = on_quit
        self.on_toggle_mini = on_toggle_mini
        self.on_sync = on_sync
        self.on_settings = on_settings
        self.on_theme = on_theme
        self.theme_pref = (theme_pref or "auto").lower()
        self._nid = NOTIFYICONDATAW()
        self._hicon = None
        self._added = False

    # ------------------------------------------------------------------
    def start(self):
        if self._hicon:
            user32.DestroyIcon(self._hicon)
            self._hicon = None
        self._hicon = _make_hicon(32)
        nid = self._nid
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.window.hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = "TokenBoard"
        if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            self._added = True
            # 用 v4 才能收到 WM_LBUTTONUP 之类的精细事件
            nid.uTimeoutOrVersion = NOTIFYICON_VERSION_4
            shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
        return self._added

    def recreate(self) -> bool:
        """Explorer 重启后图标会被清空，重新注册一次。"""
        if self._added:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            self._added = False
        return self.start()

    def set_title(self, text: str):
        if not self._added:
            return
        self._nid.uFlags = NIF_TIP
        self._nid.szTip = text[:127]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def stop(self):
        if self._added:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            self._added = False
        if self._hicon:
            user32.DestroyIcon(self._hicon)
            self._hicon = None

    # ------------------------------------------------------------------
    def handle(self, wparam: int, lparam: int):
        """处理托盘回调。"""
        event = lparam & 0xFFFF
        if event == 0x0202:          # WM_LBUTTONUP
            self.on_show()
        elif event == 0x0205:        # WM_RBUTTONUP
            self._popup_menu()
        elif event == 0x007B:        # WM_CONTEXTMENU
            self._popup_menu()

    def _popup_menu(self):
        hmenu = user32.CreatePopupMenu()
        user32.AppendMenuW(hmenu, 0, WM_SHOW_ID, "显示 / 隐藏面板")
        user32.AppendMenuW(hmenu, 0, WM_REFRESH_ID, "立即刷新")
        if self.on_sync is not None or self.on_settings is not None:
            user32.AppendMenuW(hmenu, 0, 0x0800, "")     # MF_SEPARATOR
        if self.on_sync is not None:
            user32.AppendMenuW(hmenu, 0, WM_SYNC_ID, "立即同步（WebDAV）")
        if self.on_settings is not None:
            user32.AppendMenuW(hmenu, 0, WM_SETTINGS_ID, "设置…")
        if self.on_theme is not None:
            sub = user32.CreatePopupMenu()
            user32.AppendMenuW(sub, 0, WM_THEME_AUTO, "跟随系统")
            user32.AppendMenuW(sub, 0, WM_THEME_LIGHT, "浅色")
            user32.AppendMenuW(sub, 0, WM_THEME_DARK, "深色")
            cur = {"auto": WM_THEME_AUTO, "light": WM_THEME_LIGHT,
                   "dark": WM_THEME_DARK}.get(self.theme_pref, WM_THEME_AUTO)
            # 单选打勾：三段 id 连续，方便 CheckMenuRadioItem 一次标好
            user32.CheckMenuRadioItem(sub, WM_THEME_AUTO, WM_THEME_DARK, cur, 0)
            user32.AppendMenuW(hmenu, MF_POPUP, sub, "外观")
        if self.on_toggle_mini is not None:
            user32.AppendMenuW(hmenu, 0, WM_MINI_ID, "显示 / 隐藏桌面小框")
        user32.AppendMenuW(hmenu, 0, 0x0800, "")     # MF_SEPARATOR
        user32.AppendMenuW(hmenu, 0, WM_QUIT_ID, "退出 TokenBoard")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.window.hwnd)
        cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.window.hwnd, None)
        user32.PostMessageW(self.window.hwnd, 0x0100, 0, 0)   # WM_NULL
        user32.DestroyMenu(hmenu)

        if cmd == WM_SHOW_ID:
            self.on_show()
        elif cmd == WM_REFRESH_ID:
            self.on_refresh()
        elif cmd == WM_SYNC_ID and self.on_sync is not None:
            self.on_sync()
        elif cmd == WM_SETTINGS_ID and self.on_settings is not None:
            self.on_settings()
        elif cmd in (WM_THEME_AUTO, WM_THEME_LIGHT, WM_THEME_DARK) \
                and self.on_theme is not None:
            pref = {WM_THEME_AUTO: "auto", WM_THEME_LIGHT: "light",
                    WM_THEME_DARK: "dark"}[cmd]
            self.theme_pref = pref
            self.on_theme(pref)
        elif cmd == WM_MINI_ID and self.on_toggle_mini is not None:
            self.on_toggle_mini()
        elif cmd == WM_QUIT_ID:
            self.on_quit()
