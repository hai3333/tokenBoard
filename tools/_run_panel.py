"""Direct harness: create Panel in-process, force draw, print exceptions."""
from __future__ import annotations

import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tokenboard.config import DB_PATH  # noqa: E402
from tokenboard.pricing import get_pricing  # noqa: E402
from tokenboard.scanner import Scanner  # noqa: E402
from tokenboard.store import Store  # noqa: E402
from tokenboard.ui import panel as P  # noqa: E402
from tokenboard.ui.win32 import MSG, user32, gdi32  # noqa: E402

import logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")


def pump(ms: int) -> None:
    msg = MSG()
    end = time.time() + ms / 1000
    n = 0
    while time.time() < end:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
            n += 1
        time.sleep(0.01)
    print("pumped msgs:", n)


def repaint(p) -> None:
    RDW_INVALIDATE, RDW_UPDATENOW, RDW_ALLCHILDREN = 0x0001, 0x0100, 0x0080
    user32.RedrawWindow(p.hwnd, None, None,
                        RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN)
    pump(300)


def main() -> int:
    store = Store(DB_PATH)
    store.load_pricing(get_pricing().pricing_map())
    scanner = Scanner(store)
    p = P.Panel(store, scanner)
    p.create()
    p.show()
    pump(1500)
    repaint(p)
    print("hwnd:", p.hwnd)
    print("rows:", len(p._rows))
    p.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
