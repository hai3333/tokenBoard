"""TokenBoard 桌面端入口（PyInstaller 打包用）。

放在项目根目录，用绝对导入打包，避免相对导入在单文件模式下失效。
"""
import sys

from tokenboard.app import main

if __name__ == "__main__":
    sys.exit(main())
