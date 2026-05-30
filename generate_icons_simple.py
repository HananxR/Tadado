# -*- coding: utf-8 -*-
"""Generate simple app icons using PySide6 QPainter - single file, no deps."""
import math
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

RESOURCES = Path(__file__).resolve().parent / "resources" / "icons"
RESOURCES.mkdir(parents=True, exist_ok=True)

PRIMARY = QColor("#5b8def")
WHITE = QColor("#ffffff")
DARK = QColor("#2c2c2c")


def render(draw_func, size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_func(p, size)
    p.end()
    # Save to bytes
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(buf.data()), pm


def save_png(pm, path):
    pm.save(str(path), "PNG")


def save_png_bytes(data, path):
    with open(path, "wb") as f:
        f.write(data)


def arrow_head(p, tip, angle_deg, sz):
    rad = math.radians(angle_deg)
    p.drawLine(tip, QPointF(tip.x() + sz * math.cos(rad + 2.6), tip.y() - sz * math.sin(rad + 2.6)))
    p.drawLine(tip, QPointF(tip.x() + sz * math.cos(rad - 2.6), tip.y() - sz * math.sin(rad - 2.6)))


# --- Icon drawing functions ---

def draw_app(p, sz):
    """New logo: rounded tile with task-list motif (3 lines + checkmark on top line)."""
    m = sz * 0.10
    box = QRectF(m, m, sz - 2 * m, sz - 2 * m)
    r = sz * 0.16
    # Tile background
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(box, r, r)

    # Three task lines
    line_pen = QPen(WHITE)
    lw = max(1.5, sz * 0.055)
    line_pen.setWidthF(lw)
    line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(line_pen)

    lx = sz * 0.22
    lw_max = sz * 0.56
    cy_center = sz / 2
    gap = sz * 0.14

    # Three horizontal lines, top one slightly shorter (checkmark on it)
    # Top line with checkmark
    y1 = cy_center - gap
    p.drawLine(QPointF(lx, y1), QPointF(lx + lw_max * 0.55, y1))
    # Checkmark on top line
    cm = sz * 0.08
    cx = lx + lw_max * 0.42
    cy = y1
    p.drawLine(QPointF(cx, cy + cm * 0.3), QPointF(cx + cm * 0.7, cy + cm * 1.0))
    p.drawLine(QPointF(cx + cm * 0.7, cy + cm * 1.0), QPointF(cx + cm * 1.7, cy - cm * 0.7))

    # Middle line (full width)
    p.drawLine(QPointF(lx, cy_center), QPointF(lx + lw_max, cy_center))

    # Bottom line (shorter, lighter)
    bp = QPen(QColor(255, 255, 255, 150), lw)
    bp.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(bp)
    p.drawLine(QPointF(lx, cy_center + gap), QPointF(lx + lw_max * 0.65, cy_center + gap))


def draw_tray(p, sz):
    """Tray icon: simplified tile with two lines — readable at 16px."""
    if sz <= 16:
        m = 1.5
        r = 3.5
        lw = 1.8
    else:
        m = sz * 0.14
        r = sz * 0.18
        lw = max(2.0, sz * 0.07)

    box = QRectF(m, m, sz - 2 * m, sz - 2 * m)
    # Tile
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(box, r, r)

    # Two white lines inside
    pen = QPen(WHITE, lw)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)

    lx = sz * 0.25
    lw_max = sz * 0.50
    gap = sz * 0.15
    cy_c = sz / 2

    # Top line (shorter = with checkmark)
    p.drawLine(QPointF(lx, cy_c - gap), QPointF(lx + lw_max * 0.5, cy_c - gap))
    # Small checkmark
    cx, cy1 = lx + lw_max * 0.35, cy_c - gap
    cs = sz * 0.10
    p.drawLine(QPointF(cx, cy1 + cs * 0.3), QPointF(cx + cs * 0.6, cy1 + cs))
    p.drawLine(QPointF(cx + cs * 0.6, cy1 + cs), QPointF(cx + cs * 1.4, cy1 - cs * 0.6))

    # Bottom line (full width)
    p.drawLine(QPointF(lx, cy_c + gap), QPointF(lx + lw_max, cy_c + gap))


def draw_refresh(p, sz):
    cx, cy = sz / 2, sz / 2
    r = sz * 0.32
    p.setPen(QPen(DARK, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    arc = QRectF(cx - r, cy - r, r * 2, r * 2)
    p.drawArc(arc, 50 * 16, 280 * 16)
    arrow_head(p, QPointF(cx + r * 0.86, cy - r * 0.5), 120, sz * 0.11)
    p.drawArc(arc, 230 * 16, 280 * 16)
    arrow_head(p, QPointF(cx - r * 0.86, cy + r * 0.5), -60, sz * 0.11)


def draw_heatmap(p, sz):
    m = sz * 0.15
    cols, rows = 5, 4
    gap = sz * 0.04
    cw = (sz - 2 * m - (cols - 1) * gap) / cols
    ch = (sz - 2 * m - (rows - 1) * gap) / rows
    shades = ["#d4d4d4", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    p.setPen(Qt.PenStyle.NoPen)
    for col in range(cols):
        for row in range(rows):
            x = m + col * (cw + gap)
            y = m + row * (ch + gap)
            idx = (col * rows + row) % len(shades)
            p.setBrush(QColor(shades[idx]))
            p.drawRoundedRect(QRectF(x, y, cw, ch), 2, 2)


def draw_import(p, sz):
    m = sz * 0.14
    cx = sz / 2
    p.setPen(QPen(DARK, 2.0))
    ay, ah = m * 1.2, sz * 0.42
    p.drawLine(QPointF(cx, ay), QPointF(cx, ay + ah))
    arrow_head(p, QPointF(cx, ay + ah), 90, sz * 0.10)
    by_, bh = ay + ah + sz * 0.08, sz - (ay + ah + sz * 0.08) - m
    bw = sz * 0.5
    p.setBrush(QBrush(QColor("#eaeae5")))
    p.drawRoundedRect(QRectF(cx - bw / 2, by_, bw, bh), sz * 0.05, sz * 0.05)


def draw_export(p, sz):
    m = sz * 0.14
    cx = sz / 2
    p.setPen(QPen(DARK, 2.0))
    by_, bh = m * 1.8, sz * 0.32
    bw = sz * 0.5
    p.setBrush(QBrush(QColor("#eaeae5")))
    p.drawRoundedRect(QRectF(cx - bw / 2, by_, bw, bh), sz * 0.05, sz * 0.05)
    ay = by_ + bh + sz * 0.08
    ah = sz - ay - m
    p.drawLine(QPointF(cx, ay), QPointF(cx, ay + ah))
    arrow_head(p, QPointF(cx, ay), -90, sz * 0.10)


def draw_settings(p, sz):
    cx, cy = sz / 2, sz / 2
    or_, ir = sz * 0.32, sz * 0.14
    p.setPen(QPen(DARK, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), or_, or_)
    p.drawEllipse(QPointF(cx, cy), ir, ir)
    for i in range(8):
        rad = math.radians(i * 45)
        x1 = cx + (or_ - sz * 0.02) * math.cos(rad)
        y1 = cy - (or_ - sz * 0.02) * math.sin(rad)
        x2 = cx + (or_ + sz * 0.08) * math.cos(rad)
        y2 = cy - (or_ + sz * 0.08) * math.sin(rad)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def draw_new(p, sz):
    cx, cy = sz / 2, sz / 2
    r = sz * 0.34
    p.setPen(QPen(PRIMARY, 2.0))
    p.setBrush(QBrush(PRIMARY.darker(110)))
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setPen(QPen(WHITE, max(2, sz * 0.07)))
    arm = r * 0.55
    p.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
    p.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))


def draw_new_multi(p, sz):
    """Multi task: two overlapping document tiles with a small plus badge."""
    m = sz * 0.12
    bw, bh = sz * 0.48, sz * 0.52
    # Back document
    bx = sz * 0.20
    by_ = sz * 0.16
    p.setPen(QPen(PRIMARY.darker(120), 1.5))
    p.setBrush(QBrush(PRIMARY.lighter(140)))
    p.drawRoundedRect(QRectF(bx, by_, bw, bh), 3, 3)
    # Front document
    fx = sz * 0.32
    fy = sz * 0.28
    p.setPen(QPen(PRIMARY, 2.0))
    p.setBrush(QBrush(PRIMARY))
    p.drawRoundedRect(QRectF(fx, fy, bw, bh), 3, 3)
    # Lines on front document
    lw2 = max(1, sz * 0.04)
    p.setPen(QPen(WHITE, lw2))
    lx = fx + sz * 0.09
    lmax = bw - sz * 0.18
    p.drawLine(QPointF(lx, fy + bh * 0.35), QPointF(lx + lmax, fy + bh * 0.35))
    p.drawLine(QPointF(lx, fy + bh * 0.55), QPointF(lx + lmax * 0.7, fy + bh * 0.55))
    p.drawLine(QPointF(lx, fy + bh * 0.75), QPointF(lx + lmax * 0.5, fy + bh * 0.75))
    # Small plus badge
    badge_cx = fx + bw - sz * 0.02
    badge_cy = fy + sz * 0.02
    badge_r = sz * 0.12
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(WHITE))
    p.drawEllipse(QPointF(badge_cx, badge_cy), badge_r, badge_r)
    p.setPen(QPen(PRIMARY, max(1.5, sz * 0.05)))
    arm2 = badge_r * 0.5
    p.drawLine(QPointF(badge_cx - arm2, badge_cy), QPointF(badge_cx + arm2, badge_cy))
    p.drawLine(QPointF(badge_cx, badge_cy - arm2), QPointF(badge_cx, badge_cy + arm2))


def draw_task_manage(p, sz):
    """Task management: checklist with checkbox on top line."""
    m = sz * 0.16
    # Document background
    p.setPen(QPen(DARK, 2.0))
    p.setBrush(QBrush(QColor("#f0efe9")))
    p.drawRoundedRect(QRectF(m, m, sz - 2 * m, sz - 2 * m), 4, 4)
    # Three lines
    lx = sz * 0.22
    lw_max = sz * 0.60
    gap = sz * 0.16
    cy_c = sz / 2
    lw3 = max(1.5, sz * 0.05)
    p.setPen(QPen(DARK, lw3))
    p.drawLine(QPointF(lx, cy_c - gap), QPointF(lx + lw_max, cy_c - gap))
    p.drawLine(QPointF(lx, cy_c), QPointF(lx + lw_max * 0.8, cy_c))
    p.drawLine(QPointF(lx, cy_c + gap), QPointF(lx + lw_max * 0.6, cy_c + gap))
    # Checkbox on top line
    cb_size = sz * 0.18
    cb_x = lx - sz * 0.04
    cb_y = cy_c - gap - cb_size / 2
    p.setPen(QPen(PRIMARY, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(cb_x, cb_y, cb_size, cb_size), 2, 2)
    # Checkmark
    p.setPen(QPen(PRIMARY, max(1.5, sz * 0.05)))
    cm2 = cb_size * 0.3
    cx2 = cb_x + cb_size * 0.22
    cy2 = cb_y + cb_size * 0.5
    p.drawLine(QPointF(cx2, cy2), QPointF(cx2 + cm2, cy2 + cm2))
    p.drawLine(QPointF(cx2 + cm2, cy2 + cm2), QPointF(cx2 + cm2 * 2.2, cy2 - cm2 * 0.8))


def draw_help(p, sz):
    """Help: question mark inside a circle."""
    cx, cy = sz / 2, sz / 2
    r = sz * 0.34
    p.setPen(QPen(DARK, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), r, r)
    # Question mark
    qm = sz * 0.12
    p.setPen(QPen(DARK, max(2, sz * 0.07)))
    # Top curve of ?
    qx, qy = cx, cy - r * 0.3
    p.drawArc(QRectF(qx - qm, qy - qm, qm * 2, qm * 2), 0, 180 * 16)
    # Vertical stroke
    p.drawLine(QPointF(cx + qm * 0.4, cy + r * 0.05), QPointF(cx, cy - r * 0.05))
    # Dot
    p.setBrush(QBrush(DARK))
    p.drawEllipse(QPointF(cx, cy + r * 0.45), sz * 0.04, sz * 0.04)


def draw_tray_hide(p, sz):
    """Minimize to tray: simple box with down arrow — matches settings/help style."""
    m = sz * 0.18
    bw, bh = sz * 0.42, sz * 0.38
    bx = (sz - bw) / 2
    by_ = sz - m - bh
    p.setPen(QPen(DARK, 2.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(bx, by_, bw, bh), 3, 3)
    # Downward arrow centered above the box
    ax = sz / 2
    ay_top = m + sz * 0.06
    ay_bot = by_ - sz * 0.06
    p.drawLine(QPointF(ax, ay_top), QPointF(ax, ay_bot))
    arrow_head(p, QPointF(ax, ay_bot), 90, sz * 0.10)
    # Horizontal line in box
    lx = bx + sz * 0.10
    lw = bw - sz * 0.20
    ly = by_ + bh * 0.55
    p.drawLine(QPointF(lx, ly), QPointF(lx + lw, ly))


def draw_fullscreen_toggle(p, sz):
    """Fullscreen toggle: two corner brackets — matches settings/help style."""
    m = sz * 0.16
    inner = sz * 0.10
    arm = sz * 0.24
    p.setPen(QPen(DARK, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    # Top-left bracket (┌ shape)
    p.drawLine(QPointF(m, m + arm), QPointF(m, m))
    p.drawLine(QPointF(m, m), QPointF(m + arm, m))
    # Bottom-right bracket (┘ shape)
    brx = sz - m
    bry = sz - m
    p.drawLine(QPointF(brx - arm, bry), QPointF(brx, bry))
    p.drawLine(QPointF(brx, bry - arm), QPointF(brx, bry))
    # Arrow heads indicating outward expansion
    arrow_head(p, QPointF(m, m), -135, sz * 0.08)
    arrow_head(p, QPointF(brx, bry), 45, sz * 0.08)


def draw_window_close(p, sz):
    """Close window: clean X mark — matches settings/help style."""
    m = sz * 0.24
    p.setPen(QPen(DARK, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(m, m), QPointF(sz - m, sz - m))
    p.drawLine(QPointF(sz - m, m), QPointF(m, sz - m))


def build_ico(draw_func, sizes):
    frames = [render(draw_func, s)[0] for s in sizes]
    buf = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    for i, d in enumerate(frames):
        w = sizes[i] if sizes[i] < 256 else 0
        h = sizes[i] if sizes[i] < 256 else 0
        buf += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(d), offset)
        offset += len(d)
    for d in frames:
        buf += d
    return buf


# --- Generate ---

app = QApplication(sys.argv)

SIZES = [16, 24, 32, 48, 256]

ICONS = {
    "app": draw_app,
    "tray_normal": draw_tray,
    "refresh": draw_refresh,
    "heatmap": draw_heatmap,
    "import": draw_import,
    "export": draw_export,
    "settings": draw_settings,
    "new_task": draw_new,
    "new_multi_task": draw_new_multi,
    "task_manage": draw_task_manage,
    "help": draw_help,
    "tray_hide": draw_tray_hide,
    "fullscreen_toggle": draw_fullscreen_toggle,
    "window_close": draw_window_close,
}

for name, func in ICONS.items():
    for sz in SIZES:
        data, pm = render(func, sz)
        save_png(pm, RESOURCES / f"{name}_{sz}.png")
    # Default 24px
    _, pm24 = render(func, 24)
    save_png(pm24, RESOURCES / f"{name}.png")
    print(f"  {name}.png (24px + {len(SIZES)} multi-size)")

# ICO files
for name, func in [("app", draw_app), ("tray_normal", draw_tray)]:
    ico = build_ico(func, [16, 32, 48, 256])
    save_png_bytes(ico, RESOURCES / f"{name}.ico")
    print(f"  {name}.ico (16/32/48/256)")

print("All icons generated.")
app.quit()
