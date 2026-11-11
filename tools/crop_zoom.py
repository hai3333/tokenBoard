"""裁剪放大截图的局部，用来肉眼检查间距/接缝。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/screen_mini.png")
box = tuple(int(v) for v in sys.argv[2:6]) if len(sys.argv) >= 6 else (0, 0, 220, 110)
scale = float(sys.argv[6]) if len(sys.argv) >= 7 else 3.0
out = Path(sys.argv[7]) if len(sys.argv) >= 8 else Path("tools/zoom.png")

im = Image.open(src)
im.crop(box).resize((int((box[2] - box[0]) * scale),
                     int((box[3] - box[1]) * scale)), Image.LANCZOS).save(out)
print("saved", out)
