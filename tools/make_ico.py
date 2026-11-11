#!/usr/bin/env python3
"""生成打包用的 tokenboard.ico（复用运行时同一套像素算法）。

托盘图标是运行时用纯 Python 算的；这里只把同样的像素导出成 .ico，
让「开始菜单/桌面快捷方式/任务栏」的图标也一致。
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenboard.icon import make_icon_bits  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "build", "tokenboard.ico")


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = []
    for s in sizes:
        w, h, bits = make_icon_bits(s)
        img = Image.frombytes("RGBA", (w, h), bytes(bits))
        frames.append(img)
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in sizes],
                     append_images=frames[:-1])
    print("wrote", OUT, os.path.getsize(OUT), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
