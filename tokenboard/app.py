"""应用入口：装配 store / scanner / 面板 / 托盘。

刻意不引入 tkinter / Pillow / pystray —— 换成原生 Win32 后常驻内存从
约 65MB 降到 20MB 上下，对一个后台常驻的托盘插件差别很大。
"""
from __future__ import annotations

import logging
import sys
import traceback

from . import ipc
from .config import DB_PATH, LOG_PATH, ensure_dirs
from .pricing import get_pricing
from .scanner import Scanner
from .store import Store
from .ui.mini import MiniBar
from .ui.panel import Panel
from .ui.tray import Tray

_LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def _dpi_system() -> int | str:
    """诊断用：拿一下系统 DPI（拿不到就返回异常名）。"""
    try:
        import ctypes
        return ctypes.windll.user32.GetDpiForSystem()
    except Exception as e:  # noqa: BLE001
        return type(e).__name__


def _dpi_awareness() -> str:
    """诊断用：当前进程的 DPI 感知上下文。"""
    try:
        from .ui.win32 import dpi_awareness_state
        return dpi_awareness_state()
    except Exception as e:  # noqa: BLE001
        return type(e).__name__


def setup_logging() -> None:
    ensure_dirs()
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_PATH, encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, handlers=handlers)


def main() -> int:
    # --uninstall：走「应用和功能」里的卸载入口
    if "--uninstall" in sys.argv:
        from .install import uninstall
        uninstall(remove_data="--purge" in sys.argv)
        return 0

    setup_logging()
    log = logging.getLogger("tokenboard")

    # --sync-settings：让正在跑的实例打开同步设置（也方便做快捷方式）
    want_sync = "--sync-settings" in sys.argv

    # 已有实例在跑？-> 通知它把面板显示出来，本次直接退出。
    # 这样「窗口收进托盘后找不到了」的问题不存在了：再点一次启动即可唤回。
    if ipc.notify_existing(b"sync\n" if want_sync else b"show\n"):
        log.info("检测到已有实例，已请求%s",
                 "打开同步设置" if want_sync else "显示面板")
        return 0

    try:
        store = Store(DB_PATH)
        store.load_pricing(get_pricing().pricing_map())

        # 速度采样是新增的：老库里的日志文件早就被水量跳过过了，
        # 不清一次水位的话历史轮次永远不会回填首字/耗时。
        if not store.get_meta("speed_backfill_v2"):
            store.clear_sync()
            store.set_meta("speed_backfill_v2", True)
            log.info("首次升级：已清空扫描水位，本轮将回填速度采样")

        # ---- 外观：先按偏好套主题，再建窗口（否则首帧会闪默认色）
        from .ui import theme as theme_mod
        theme_pref = {"v": (store.get_meta("theme") or "auto").lower()}
        theme_mod.apply(theme_pref["v"])

        scanner = Scanner(store)
        panel = Panel(store, scanner)
        # 打一行 DPI 信息：打包后在 150% 缩放下如果这里不是 1.5，
        # 说明 exe 的 manifest 没生效（界面会按 1.0 倍画，窗口只有 880x520 物理像素）。
        # 感知上下文要一起看：UNAWARE 就意味着窗口被系统虚拟化，
        # 界面会缩成一小块，而且所有鼠标坐标都要打折扣。
        log.info("DPI 缩放 %.2f（GetDpiForSystem=%s，感知=%s）",
                 panel.scale, _dpi_system(), _dpi_awareness())

        # ---- 桌面常驻小框：一直挂在桌面上，点一下展开主面板
        mini = MiniBar(store, on_expand=panel.on_show_requested)
        mini.start()

        def toggle_mini():
            if mini.visible:
                mini.hide()
            else:
                mini.show()
                mini.set_topmost(True)

        # ---- 外观切换：面板 / 小框 / 设置窗一起换，偏好写进库
        def set_theme(pref: str):
            pref = (pref or "auto").lower()
            theme_pref["v"] = pref
            try:
                store.set_meta("theme", pref)
            except Exception:  # noqa: BLE001
                pass
            try:
                panel.apply_theme(pref)
            except Exception:  # noqa: BLE001
                pass
            try:
                mini.apply_theme(pref)
            except Exception:  # noqa: BLE001
                pass
            w = panel.sync_win
            if w is not None:
                try:
                    w.apply_theme(pref)
                except Exception:  # noqa: BLE001
                    pass
            try:
                panel.tray.theme_pref = pref
            except Exception:  # noqa: BLE001
                pass
            log.info("外观切换为 %s（生效 %s）", pref, theme_mod.MODE)

        # ---- WebDAV 云同步：设置窗口用到才建（没人点就不占内存）
        def open_sync_settings():
            log.info("打开设置窗口")
            w = panel.sync_win
            if w is None or not getattr(w, "hwnd", None):
                from .ui.syncwin import SyncWindow
                w = SyncWindow(store, on_changed=panel.reload_sync,
                               on_theme=set_theme, theme_pref=theme_pref["v"])
                w.create()
                panel.sync_win = w
            w.show()
            w.bring_to_front()

        def sync_now():
            # 没配置时直接把设置窗打开，别让「立即同步」点了没反应
            if not panel.sync_now(force=True):
                open_sync_settings()

        def quit_all():
            try:
                panel.tray.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                if panel.sync_win is not None:
                    panel.sync_win.destroy()
            except Exception:  # noqa: BLE001
                pass
            try:
                server.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                store.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                panel.destroy()
            except Exception:  # noqa: BLE001
                pass
            try:
                mini.destroy()
            except Exception:  # noqa: BLE001
                pass

        server = ipc.Server(panel.on_show_requested,
                            on_settings=panel.request_sync_window)
        server.start()
        # 主线程里真正建窗口的回调（IPC 只负责发请求）
        panel.on_sync_settings_request = open_sync_settings

        tray = Tray(panel,
                    on_show=panel.on_show_requested,
                    on_refresh=panel._start_scan,
                    on_quit=quit_all,
                    on_toggle_mini=toggle_mini,
                    on_sync=sync_now,
                    on_settings=open_sync_settings,
                    on_theme=set_theme,
                    theme_pref=theme_pref["v"])
        panel.tray = tray
        panel.on_quit = quit_all
        panel.on_open_settings = open_sync_settings

        panel.start()
        if tray.start():
            log.info("托盘图标已注册")
        else:
            # 之前这里不看返回值，托盘图标注册失败也是静默的，
            # 表现就是「托盘里找不到图标」却查不出原因。
            log.warning("托盘图标注册失败（Shell_NotifyIcon 返回失败）")
        log.info("TokenBoard 启动，数据目录 %s", DB_PATH.parent)
        if want_sync:
            # 冷启动就带着 --sync-settings：起来后直接把设置窗摆出来
            open_sync_settings()
        panel.run()
    except Exception:  # noqa: BLE001
        log.error("启动失败:\n%s", traceback.format_exc())
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
