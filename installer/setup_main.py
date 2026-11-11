"""TokenBoard 安装器入口（被 PyInstaller 打包成 TokenBoard-Setup.exe）。

payload 是应用本体（dist/TokenBoard），打包时作为数据一起塞进 exe。
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenboard import install as inst  # noqa: E402

VERSION = "1.0.0"
BANNER = r"""
  ______          _        _                _
 |___  /__  ___ _| |_ __ _| |__  _ __ ___ | |__
    / / _ \/ _ \ | __/ _` | '_ \| '_ ` _ \| '_ \
   / /  __/  __/ | || (_| | |_) | | | | | | |_) |
  /_/   \___|\___| \__\__,_|_.__/|_| |_| |_| .__/
                                            |_|
"""


def payload_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "payload"
    return Path(__file__).resolve().parents[1] / "dist" / "TokenBoard"


def main() -> int:
    print(BANNER)
    print(f"  TokenBoard 安装程序  v{VERSION}")
    print("  " + "=" * 46)
    print()

    src = payload_dir()
    if not src.is_dir():
        print(f"[错误] 找不到应用包：{src}")
        input("按回车退出...")
        return 1

    dest = inst.default_install_dir()
    desktop = True

    if "--uninstall" in sys.argv:
        print("正在卸载 TokenBoard ...")
        inst.uninstall(dest, remove_data="--purge" in sys.argv)
        print("卸载完成。")
        input("按回车退出...")
        return 0

    print(f"  安装位置：{dest}")
    print(f"  桌面快捷方式：{'创建' if desktop else '不创建'}")
    print()
    try:
        answer = input("  按回车开始安装（输入 n 取消）：").strip().lower()
    except EOFError:
        answer = ""
    if answer == "n":
        print("已取消。")
        return 0

    t0 = time.time()
    try:
        inst.install(src, dest, with_desktop=desktop, version=VERSION)
    except Exception as e:  # noqa: BLE001
        print(f"\n[失败] 安装出错：{e}")
        input("按回车退出...")
        return 1

    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"\n  [完成] 已安装到 {dest}  ({size / 1024 / 1024:.1f} MB, "
          f"{time.time() - t0:.1f}s)")
    print("  · 开始菜单已创建「TokenBoard」快捷方式")
    print("  · 控制面板「应用」里可以卸载")

    try:
        answer = input("\n  立即启动 TokenBoard？(Y/n) ").strip().lower()
    except EOFError:
        answer = "y"
    if answer != "n":
        subprocess.Popen([str(dest / "TokenBoard.exe")], cwd=str(dest))
        print("  已启动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
