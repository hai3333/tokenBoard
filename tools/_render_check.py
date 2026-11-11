"""Force _render_to() into a memory DC and surface any exception."""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tokenboard.config import DB_PATH  # noqa: E402
from tokenboard.pricing import get_pricing  # noqa: E402
from tokenboard.scanner import Scanner  # noqa: E402
from tokenboard.store import Store  # noqa: E402
from tokenboard.ui import panel as P  # noqa: E402
from tokenboard.ui.win32 import user32, gdi32  # noqa: E402


def main() -> int:
    store = Store(DB_PATH)
    store.load_pricing(get_pricing().pricing_map())
    scanner = Scanner(store)
    p = P.Panel(store, scanner)
    p.create()

    hdc_screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc_screen)
    w, h = int(p.width * p.scale), int(p.height * p.scale)
    bmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(mem, bmp)
    try:
        p._render_to(mem)
        print("render_to: no exception")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, hdc_screen)
    p.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
