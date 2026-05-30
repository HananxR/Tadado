"""Phosphor-style icon drawing functions — all icons use text_primary color.

Each function signature: draw_xxx(painter: QPainter, rect: QRectF, color: QColor)
All draw within the given rect, centered, with consistent 2px stroke weight.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

_LW = 2.0  # Consistent line width for all outline icons


def _pen(color: QColor, lw: float = _LW) -> QPen:
    p = QPen(color, lw)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _circle_path(cx: float, cy: float, r: float) -> QPainterPath:
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


def _arc_path(cx: float, cy: float, r: float, start: float, span: float) -> QPainterPath:
    p = QPainterPath()
    p.arcMoveTo(QRectF(cx - r, cy - r, r * 2, r * 2), start)
    p.arcTo(QRectF(cx - r, cy - r, r * 2, r * 2), start, span)
    return p


# ═══════════════════════════════════════════════════════════════
# App / Logo
# ═══════════════════════════════════════════════════════════════

def draw_app(p: QPainter, r: QRectF, color: QColor) -> None:
    """Rounded square with four inner squares (SquaresFour / app grid)."""
    m = r.width() * 0.12
    box = QRectF(r.x() + m, r.y() + m, r.width() - 2 * m, r.height() - 2 * m)
    cr = r.width() * 0.08
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(box, cr, cr)
    # Four inner squares
    iw = box.width() * 0.30
    ih = box.height() * 0.30
    gap = box.width() * 0.10
    cx = box.center().x()
    cy = box.center().y()
    off = iw / 2 + gap / 2
    for dx, dy in [(-off, -off), (off, -off), (-off, off), (off, off)]:
        p.drawRoundedRect(QRectF(cx + dx - iw / 2, cy + dy - ih / 2, iw, ih), cr * 0.6, cr * 0.6)


# ═══════════════════════════════════════════════════════════════
# Nav icons
# ═══════════════════════════════════════════════════════════════

def draw_new_task(p: QPainter, r: QRectF, color: QColor) -> None:
    """Circle with plus (PlusCircle)."""
    cr = r.width() * 0.36
    cx, cy = r.center().x(), r.center().y()
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), cr, cr)
    arm = cr * 0.5
    p.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
    p.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))


def draw_new_multi_task(p: QPainter, r: QRectF, color: QColor) -> None:
    """Two overlapping squares (Stack)."""
    m = r.width() * 0.16
    sq = r.width() * 0.40
    ox, oy = r.width() * 0.12, r.height() * 0.12
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Back square (top-left offset)
    p.drawRoundedRect(QRectF(r.x() + m + ox, r.y() + m + oy, sq, sq), 5, 5)
    # Front square (bottom-right offset)
    p.drawRoundedRect(QRectF(r.x() + m, r.y() + m, sq, sq), 5, 5)


def draw_heatmap(p: QPainter, r: QRectF, color: QColor) -> None:
    """Grid of 4×3 dots (GridFour)."""
    cols, rows = 4, 3
    m = r.width() * 0.18
    gap = r.width() * 0.06
    cw = (r.width() - 2 * m - (cols - 1) * gap) / cols
    ch = (r.height() - 2 * m - (rows - 1) * gap) / rows
    dot_r = cw * 0.38
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for col in range(cols):
        for row in range(rows):
            p.drawEllipse(QPointF(r.x() + m + col * (cw + gap) + cw / 2,
                                   r.y() + m + row * (ch + gap) + ch / 2), dot_r, dot_r)


def draw_task_manage(p: QPainter, r: QRectF, color: QColor) -> None:
    """List with checkmarks (ListChecks)."""
    m = r.width() * 0.16
    lx = r.x() + m + r.width() * 0.12
    gap = r.height() * 0.20
    lw = r.width() * 0.52
    cy = r.center().y()
    p.setPen(_pen(color))
    # Three horizontal lines
    for dy in [-gap, 0, gap]:
        y = cy + dy
        p.drawLine(QPointF(lx, y), QPointF(lx + lw, y))
    # Checkmarks on first two lines
    cm = r.width() * 0.12
    for dy in [-gap, 0]:
        y = cy + dy
        cx = lx - r.width() * 0.08
        p.drawLine(QPointF(cx - cm * 0.5, y - cm * 0.1), QPointF(cx, y + cm * 0.4))
        p.drawLine(QPointF(cx, y + cm * 0.4), QPointF(cx + cm, y - cm * 0.5))


def draw_settings(p: QPainter, r: QRectF, color: QColor) -> None:
    """Gear icon (Gear)."""
    cx, cy = r.center().x(), r.center().y()
    or_ = r.width() * 0.32
    ir = r.width() * 0.14
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), or_, or_)
    p.drawEllipse(QPointF(cx, cy), ir, ir)
    # Spokes
    for i in range(8):
        rad = math.radians(i * 45)
        x1 = cx + (ir + 1) * math.cos(rad)
        y1 = cy - (ir + 1) * math.sin(rad)
        x2 = cx + or_ * math.cos(rad)
        y2 = cy - or_ * math.sin(rad)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def draw_help(p: QPainter, r: QRectF, color: QColor) -> None:
    """Question mark in circle (Question)."""
    cx, cy = r.center().x(), r.center().y()
    cr = r.width() * 0.36
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), cr, cr)
    # Question mark
    qs = cr * 0.50
    p.setPen(_pen(color, _LW))
    # Top arc of ? (approximated)
    arc_cx = cx - cr * 0.05
    arc_cy = cy - cr * 0.28
    arc_r = qs * 0.5
    p.drawArc(QRectF(arc_cx - arc_r, arc_cy - arc_r, arc_r * 2, arc_r * 2), 0, 200 * 16)
    # Vertical stroke
    p.drawLine(QPointF(cx + cr * 0.08, cy - cr * 0.05), QPointF(cx, cy + cr * 0.15))
    # Dot
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(cx, cy + cr * 0.45), cr * 0.08, cr * 0.08)


# ═══════════════════════════════════════════════════════════════
# Window control icons
# ═══════════════════════════════════════════════════════════════

def draw_tray_hide(p: QPainter, r: QRectF, color: QColor) -> None:
    """Arrow pointing down to a horizontal line (ArrowLineDown)."""
    cx, cy = r.center().x(), r.center().y()
    m = r.width() * 0.18
    p.setPen(_pen(color))
    # Downward arrow
    arrow_top = r.y() + m
    arrow_bot = cy + r.height() * 0.12
    p.drawLine(QPointF(cx, arrow_top), QPointF(cx, arrow_bot))
    # Arrow head
    ah = r.width() * 0.12
    p.drawLine(QPointF(cx - ah, arrow_bot - ah), QPointF(cx, arrow_bot))
    p.drawLine(QPointF(cx + ah, arrow_bot - ah), QPointF(cx, arrow_bot))
    # Bottom line
    line_y = r.bottom() - m
    lw = r.width() * 0.48
    p.drawLine(QPointF(cx - lw / 2, line_y), QPointF(cx + lw / 2, line_y))


def draw_fullscreen_toggle(p: QPainter, r: QRectF, color: QColor) -> None:
    """Diagonal arrows pointing outward from corners (ArrowsOut)."""
    m = r.width() * 0.14
    arm = r.width() * 0.30
    cx, cy = r.center().x(), r.center().y()
    p.setPen(_pen(color))
    # Top-left corner ┌
    tl_x, tl_y = r.x() + m, r.y() + m
    p.drawLine(QPointF(tl_x, tl_y + arm), QPointF(tl_x, tl_y))
    p.drawLine(QPointF(tl_x, tl_y), QPointF(tl_x + arm, tl_y))
    # Arrow head top-left (pointing up-left)
    ah = r.width() * 0.08
    p.drawLine(QPointF(tl_x + arm * 0.2, tl_y + ah), QPointF(tl_x, tl_y))
    p.drawLine(QPointF(tl_x + ah, tl_y + arm * 0.2), QPointF(tl_x, tl_y))
    # Bottom-right corner ┘
    br_x, br_y = r.right() - m, r.bottom() - m
    p.drawLine(QPointF(br_x - arm, br_y), QPointF(br_x, br_y))
    p.drawLine(QPointF(br_x, br_y - arm), QPointF(br_x, br_y))
    # Arrow head bottom-right (pointing down-right)
    p.drawLine(QPointF(br_x - arm * 0.2, br_y - ah), QPointF(br_x, br_y))
    p.drawLine(QPointF(br_x - ah, br_y - arm * 0.2), QPointF(br_x, br_y))


def draw_window_close(p: QPainter, r: QRectF, color: QColor) -> None:
    """X mark (X)."""
    m = r.width() * 0.22
    p.setPen(_pen(color, _LW))
    p.drawLine(QPointF(r.x() + m, r.y() + m), QPointF(r.right() - m, r.bottom() - m))
    p.drawLine(QPointF(r.right() - m, r.y() + m), QPointF(r.x() + m, r.bottom() - m))


def draw_tray(p: QPainter, r: QRectF, color: QColor) -> None:
    """App window (AppWindow) — simplified for tray icon."""
    m = r.width() * 0.14
    bw = r.width() - 2 * m
    bh = r.height() - 2 * m
    p.setPen(_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(r.x() + m, r.y() + m + bh * 0.18, bw, bh * 0.82), 4, 4)
    # Title bar divider
    p.drawLine(QPointF(r.x() + m, r.y() + m + bh * 0.30),
               QPointF(r.x() + m + bw, r.y() + m + bh * 0.30))
    # Two window control dots
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    dot_r = bw * 0.05
    dot_y = r.y() + m + bh * 0.13
    p.drawEllipse(QPointF(r.x() + m + bw * 0.12, dot_y), dot_r, dot_r)
    p.drawEllipse(QPointF(r.x() + m + bw * 0.24, dot_y), dot_r, dot_r)
    p.drawEllipse(QPointF(r.x() + m + bw * 0.36, dot_y), dot_r, dot_r)


# ═══════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════

ICON_DRAW_FUNCS = {
    "app": draw_app,
    "new_task": draw_new_task,
    "new_multi_task": draw_new_multi_task,
    "heatmap": draw_heatmap,
    "task_manage": draw_task_manage,
    "settings": draw_settings,
    "help": draw_help,
    "tray_hide": draw_tray_hide,
    "fullscreen_toggle": draw_fullscreen_toggle,
    "window_close": draw_window_close,
    "tray_normal": draw_tray,
}
