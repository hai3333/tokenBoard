"""托盘图标：纯 Python 生成像素，交给 GDI 做图标 —— 不依赖 Pillow。"""
from __future__ import annotations

import math

BLUE = (0, 122, 255)
WHITE = (255, 255, 255)


def _sdf_round_rect(px, py, cx, cy, hw, hh, r):
    """圆角矩形有符号距离场（负数在内部）。"""
    qx = abs(px - cx) - (hw - r)
    qy = abs(py - cy) - (hh - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _coverage(sdf: float) -> float:
    """距离 -> 抗锯齿覆盖率。"""
    return max(0.0, min(1.0, 0.5 - sdf))


def make_icon_bits(size: int = 32) -> tuple[int, int, bytearray]:
    """生成 ARGB 像素（自下而上的 BGRA 顺序），返回 (w, h, bytes)。"""
    pad = size * 0.055
    radius = size * 0.24
    cx = cy = size / 2.0
    hw = hh = size / 2.0 - pad

    # 三根柱子的几何（相对尺寸）
    bar_h_ratio = (0.40, 0.70, 1.0)
    inner = size * 0.27
    base_y = size - inner
    bar_area = base_y - inner
    n = 3
    gap = size * 0.085
    bar_w = (size - inner * 2 - gap * (n - 1)) / n

    buf = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            px = x + 0.5
            py = y + 0.5
            a = _coverage(_sdf_round_rect(px, py, cx, cy, hw, hh, radius))
            if a <= 0.0:
                continue
            r, g, b = BLUE

            # 白色柱子
            for i, hr in enumerate(bar_h_ratio):
                x0 = inner + i * (bar_w + gap)
                bar_cx = x0 + bar_w / 2.0
                bar_cy = base_y - bar_area * hr / 2.0
                bar_hw = bar_w / 2.0
                bar_hh = bar_area * hr / 2.0
                # 柱子端头也做成半圆（跟主图一致）
                if _coverage(_sdf_round_rect(px, py, bar_cx, bar_cy,
                                             bar_hw, bar_hh,
                                             min(bar_hw, bar_hh))) > 0.5:
                    r, g, b = WHITE
                    break

            # DIB 是 BGRA、自下而上
            off = ((size - 1 - y) * size + x) * 4
            buf[off + 0] = b
            buf[off + 1] = g
            buf[off + 2] = r
            buf[off + 3] = int(a * 255)
    return size, size, buf
