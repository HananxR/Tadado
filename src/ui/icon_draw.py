"""App icon drawing functions — filled PRIMARY-blue style matching the app logo.

All icons (except app/tray) use:
  - Fill: PRIMARY #5b8def (brand blue, consistent with app logo)
  - Details: white #ffffff
  - Rounded shapes, consistent padding

Each function signature: draw_xxx(painter: QPainter, rect: QRectF, color: QColor)
The `color` param is text_primary from design_tokens (used only by outline icons).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

PRIMARY = QColor("#5b8def")
PRIMARY_LIGHT = QColor("#7ba8f5")
WHITE = QColor("#ffffff")
DARK = QColor("#2c2c2c")

_LW = 2.0


def _pen(color: QColor, lw: float = _LW) -> QPen:
    p = QPen(color, lw)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


# ═══════════════════════════════════════════════════════════════
# App Logo — KEPT AS-IS (brand identity)
# ═══════════════════════════════════════════════════════════════

def draw_app(p: QPainter, r: QRectF, color: QColor) -> None:
    """Original app logo: blue rounded tile with white task lines + checkmark."""
    m = r.width() * 0.10
    box = QRectF(r.x() + m, r.y() + m, r.width() - 2 * m, r.height() - 2 * m)
    cr = r.width() * 0.16
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(box, cr, cr)

    lw = max(1.5, r.width() * 0.055)
    p.setPen(_pen(WHITE, lw))
    lx = r.x() + r.width() * 0.22
    lw_max = r.width() * 0.56
    cy_center = r.center().y()
    gap = r.height() * 0.14

    # Top line with checkmark (shorter)
    y1 = cy_center - gap
    p.drawLine(QPointF(lx, y1), QPointF(lx + lw_max * 0.55, y1))
    cm = r.width() * 0.08
    cx_cm = lx + lw_max * 0.42
    p.drawLine(QPointF(cx_cm, y1 + cm * 0.3), QPointF(cx_cm + cm * 0.7, y1 + cm * 1.0))
    p.drawLine(QPointF(cx_cm + cm * 0.7, y1 + cm * 1.0), QPointF(cx_cm + cm * 1.7, y1 - cm * 0.7))

    # Middle line (full)
    p.drawLine(QPointF(lx, cy_center), QPointF(lx + lw_max, cy_center))

    # Bottom line (lighter, shorter)
    p.setPen(_pen(QColor(255, 255, 255, 150), lw))
    p.drawLine(QPointF(lx, cy_center + gap), QPointF(lx + lw_max * 0.65, cy_center + gap))


# ═══════════════════════════════════════════════════════════════
# Tray icon — KEPT AS-IS
# ═══════════════════════════════════════════════════════════════

def draw_tray(p: QPainter, r: QRectF, color: QColor) -> None:
    """Simplified tray icon: blue tile with two white lines (readable at 16px)."""
    if r.width() <= 16:
        m, cr, lw = 1.5, 3.5, 1.8
    else:
        m = r.width() * 0.14
        cr = r.width() * 0.18
        lw = max(2.0, r.width() * 0.07)

    box = QRectF(r.x() + m, r.y() + m, r.width() - 2 * m, r.height() - 2 * m)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(box, cr, cr)

    p.setPen(_pen(WHITE, lw))
    lx = r.x() + r.width() * 0.25
    lw_max = r.width() * 0.50
    gap = r.height() * 0.15
    cy = r.center().y()

    p.drawLine(QPointF(lx, cy - gap), QPointF(lx + lw_max * 0.5, cy - gap))
    cx_ck, cy_ck = lx + lw_max * 0.35, cy - gap
    cs = r.width() * 0.10
    p.drawLine(QPointF(cx_ck, cy_ck + cs * 0.3), QPointF(cx_ck + cs * 0.6, cy_ck + cs))
    p.drawLine(QPointF(cx_ck + cs * 0.6, cy_ck + cs), QPointF(cx_ck + cs * 1.4, cy_ck - cs * 0.6))
    p.drawLine(QPointF(lx, cy + gap), QPointF(lx + lw_max, cy + gap))


# ═══════════════════════════════════════════════════════════════
# Nav icons — PRIMARY fill + white details, matching app logo
# ═══════════════════════════════════════════════════════════════

def draw_new_task(p: QPainter, r: QRectF, color: QColor) -> None:
    """Plus inside a filled blue circle."""
    cx, cy = r.center().x(), r.center().y()
    radius = r.width() * 0.38
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawEllipse(QPointF(cx, cy), radius, radius)
    arm = radius * 0.52
    p.setPen(_pen(WHITE, max(2, r.width() * 0.08)))
    p.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
    p.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))


def draw_new_multi_task(p: QPainter, r: QRectF, color: QColor) -> None:
    """Two overlapping rounded squares with white lines (documents), centered."""
    m = r.width() * 0.12
    sq = r.width() * 0.40
    ox = r.width() * 0.12
    oy = r.height() * 0.12
    # Center the combined shape in the rect
    cx = (r.width() - (sq + ox)) / 2
    cy = (r.height() - (sq + oy)) / 2

    # Back document (offset to bottom-right)
    bx = r.x() + cx + ox
    by_ = r.y() + cy + oy
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY_LIGHT))
    p.drawRoundedRect(QRectF(bx, by_, sq, sq), 5, 5)

    # Front document (top-left of the group)
    fx = r.x() + cx
    fy = r.y() + cy
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(QRectF(fx, fy, sq, sq), 5, 5)

    # Lines on front
    lw = max(1, r.width() * 0.04)
    p.setPen(_pen(WHITE, lw))
    llx = fx + sq * 0.20
    llw = sq * 0.60
    p.drawLine(QPointF(llx, fy + sq * 0.35), QPointF(llx + llw, fy + sq * 0.35))
    p.drawLine(QPointF(llx, fy + sq * 0.55), QPointF(llx + llw * 0.7, fy + sq * 0.55))
    p.drawLine(QPointF(llx, fy + sq * 0.75), QPointF(llx + llw * 0.5, fy + sq * 0.75))


def draw_heatmap(p: QPainter, r: QRectF, color: QColor) -> None:
    """Grid of filled rounded squares in blue gradient."""
    cols, rows = 5, 4
    m = r.width() * 0.14
    gap = r.width() * 0.05
    cw = (r.width() - 2 * m - (cols - 1) * gap) / cols
    ch = (r.height() - 2 * m - (rows - 1) * gap) / rows
    shades = [
        QColor("#d4d4d4"),  # empty
        QColor("#a8d0ff"),  # light
        QColor("#7ab5f5"),
        QColor("#5b8def"),  # PRIMARY
        QColor("#3d6fc7"),  # dark
    ]
    p.setPen(Qt.PenStyle.NoPen)
    for col in range(cols):
        for row in range(rows):
            idx = (col * rows + row) % len(shades)
            p.setBrush(QBrush(shades[idx]))
            p.drawRoundedRect(
                QRectF(r.x() + m + col * (cw + gap), r.y() + m + row * (ch + gap), cw, ch),
                2, 2,
            )


def draw_task_manage(p: QPainter, r: QRectF, color: QColor) -> None:
    """Rounded document with checkboxes — list management."""
    m = r.width() * 0.12
    box = QRectF(r.x() + m, r.y() + m, r.width() - 2 * m, r.height() - 2 * m)
    cr = r.width() * 0.12
    # Card background
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(box, cr, cr)

    # Three white lines + checkmarks
    lw = max(1.5, r.width() * 0.05)
    p.setPen(_pen(WHITE, lw))
    lx = r.x() + m + r.width() * 0.18
    lw_max = box.width() * 0.58
    cy = r.center().y()
    gap = r.height() * 0.16

    for i, dy in enumerate([-gap, 0, gap]):
        y = cy + dy
        p.drawLine(QPointF(lx, y), QPointF(lx + lw_max, y))
        if i < 2:  # Checkmark on first two lines
            cm2 = r.width() * 0.08
            cx2 = lx - r.width() * 0.06
            p.drawLine(QPointF(cx2 - cm2 * 0.4, y - cm2 * 0.1), QPointF(cx2, y + cm2 * 0.3))
            p.drawLine(QPointF(cx2, y + cm2 * 0.3), QPointF(cx2 + cm2 * 0.8, y - cm2 * 0.4))


def draw_settings(p: QPainter, r: QRectF, color: QColor) -> None:
    """Gear: filled blue circle + white spokes and cutout."""
    cx, cy = r.center().x(), r.center().y()
    or_ = r.width() * 0.36
    inner = r.width() * 0.16

    # Blue filled circle
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawEllipse(QPointF(cx, cy), or_, or_)

    # White spokes
    p.setPen(_pen(WHITE, max(2, r.width() * 0.06)))
    for i in range(8):
        rad = math.radians(i * 45)
        x1 = cx + (inner + 1) * math.cos(rad)
        y1 = cy - (inner + 1) * math.sin(rad)
        x2 = cx + or_ * math.cos(rad)
        y2 = cy - or_ * math.sin(rad)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # White inner circle (cutout)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(WHITE))
    p.drawEllipse(QPointF(cx, cy), inner, inner)
    # Blue center dot
    p.setBrush(QBrush(PRIMARY))
    p.drawEllipse(QPointF(cx, cy), inner * 0.42, inner * 0.42)


def draw_help(p: QPainter, r: QRectF, color: QColor) -> None:
    """Question mark inside filled blue circle."""
    cx, cy = r.center().x(), r.center().y()
    cr = r.width() * 0.38

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawEllipse(QPointF(cx, cy), cr, cr)

    # White question mark
    qs = cr * 0.55
    q_lw = max(2, r.width() * 0.08)
    p.setPen(_pen(WHITE, q_lw))
    # Arc
    arc_r = qs * 0.45
    p.drawArc(QRectF(cx - arc_r, cy - cr * 0.35 - arc_r, arc_r * 2, arc_r * 2), 0, 200 * 16)
    # Stem
    p.drawLine(QPointF(cx + cr * 0.06, cy - cr * 0.05), QPointF(cx, cy + cr * 0.15))
    # Dot
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(WHITE))
    p.drawEllipse(QPointF(cx, cy + cr * 0.48), max(1.5, cr * 0.10), max(1.5, cr * 0.10))


# ═══════════════════════════════════════════════════════════════
# Window control icons — minimalist, match logo style
# ═══════════════════════════════════════════════════════════════

def draw_tray_hide(p: QPainter, r: QRectF, color: QColor) -> None:
    """Down arrow to a dash (minimize to tray)."""
    cx, cy = r.center().x(), r.center().y()
    m = r.width() * 0.18
    arm = r.width() * 0.22
    p.setPen(_pen(DARK, max(2, r.width() * 0.08)))
    # Down arrow
    arrow_top = r.y() + m
    arrow_bot = cy + r.height() * 0.10
    p.drawLine(QPointF(cx, arrow_top), QPointF(cx, arrow_bot))
    ah = r.width() * 0.12
    p.drawLine(QPointF(cx - ah, arrow_bot - ah), QPointF(cx, arrow_bot))
    p.drawLine(QPointF(cx + ah, arrow_bot - ah), QPointF(cx, arrow_bot))
    # Bottom line
    line_y = r.bottom() - m
    lw = r.width() * 0.44
    p.drawLine(QPointF(cx - lw / 2, line_y), QPointF(cx + lw / 2, line_y))


def draw_fullscreen_toggle(p: QPainter, r: QRectF, color: QColor) -> None:
    """Two outward arrows from corners (expand)."""
    m = r.width() * 0.14
    arm = r.width() * 0.30
    lw = max(2, r.width() * 0.08)
    p.setPen(_pen(DARK, lw))

    # Top-left ┌
    tl = QPointF(r.x() + m, r.y() + m)
    p.drawLine(QPointF(tl.x(), tl.y() + arm), tl)
    p.drawLine(tl, QPointF(tl.x() + arm, tl.y()))
    ah = r.width() * 0.08
    p.drawLine(QPointF(tl.x() + arm * 0.18, tl.y() + ah), tl)
    p.drawLine(QPointF(tl.x() + ah, tl.y() + arm * 0.18), tl)

    # Bottom-right ┘
    br = QPointF(r.right() - m, r.bottom() - m)
    p.drawLine(QPointF(br.x() - arm, br.y()), br)
    p.drawLine(br, QPointF(br.x(), br.y() - arm))
    p.drawLine(QPointF(br.x() - arm * 0.18, br.y() - ah), br)
    p.drawLine(QPointF(br.x() - ah, br.y() - arm * 0.18), br)


def draw_window_close(p: QPainter, r: QRectF, color: QColor) -> None:
    """X mark (close)."""
    m = r.width() * 0.24
    lw = max(2, r.width() * 0.08)
    p.setPen(_pen(DARK, lw))
    p.drawLine(QPointF(r.x() + m, r.y() + m), QPointF(r.right() - m, r.bottom() - m))
    p.drawLine(QPointF(r.right() - m, r.y() + m), QPointF(r.x() + m, r.bottom() - m))


def draw_home(p: QPainter, r: QRectF, color: QColor) -> None:
    """Filled house: roof + walls + door."""
    m = r.width() * 0.08
    body_top = r.y() + r.height() * 0.42
    body = QRectF(r.x() + m, body_top, r.width() - 2 * m, r.height() - m - body_top + r.y())
    # Draw filled body
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(body, r.width() * 0.06, r.width() * 0.06)
    # Roof — triangle using QPainterPath
    roof_path = QPainterPath()
    roof_m = r.width() * 0.04
    roof_left = r.x() + roof_m
    roof_right = r.x() + r.width() - roof_m
    roof_top = r.y() + m
    roof_bottom = body_top + r.height() * 0.02
    roof_path.moveTo(roof_left, roof_bottom)
    roof_path.lineTo((roof_left + roof_right) / 2, roof_top)
    roof_path.lineTo(roof_right, roof_bottom)
    roof_path.closeSubpath()
    p.drawPath(roof_path)
    # Door — white cutout
    door_w = r.width() * 0.18
    door_h = r.height() * 0.28
    door_x = r.center().x() - door_w / 2
    door_y = body.bottom() - door_h - r.height() * 0.02
    p.setBrush(QBrush(WHITE))
    p.drawRoundedRect(QRectF(door_x, door_y, door_w, door_h), r.width() * 0.04, r.width() * 0.04)


# ═══════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════

ICON_DRAW_FUNCS = {
    "app": draw_app,
    "tray_normal": draw_tray,
    "new_task": draw_new_task,
    "new_multi_task": draw_new_multi_task,
    "heatmap": draw_heatmap,
    "task_manage": draw_task_manage,
    "settings": draw_settings,
    "help": draw_help,
    "tray_hide": draw_tray_hide,
    "fullscreen_toggle": draw_fullscreen_toggle,
    "window_close": draw_window_close,
    "home": draw_home,
}
