"""iOS-style toggle switch — capsule track with sliding thumb."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPropertyAnimation, QRectF, Qt, Property
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QWidget

from ...utils.design_tokens import get_tokens


class ToggleSwitch(QCheckBox):
    """A capsule-shaped toggle switch that animates the thumb on state change.

    Dimensions: 40×22 px.  Thumb: 16 px diameter.
    Colours driven by ``get_tokens()`` so light/dark themes work out of the box.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Internal animation position: 0.0 = OFF (left), 1.0 = ON (right)
        self._thumb_pos: float = 0.0
        self._anim: QPropertyAnimation | None = None
        self.toggled.connect(self._on_toggled)

    # ------------------------------------------------------------------
    # Animated property
    # ------------------------------------------------------------------

    def _get_thumb_pos(self) -> float:
        return self._thumb_pos

    def _set_thumb_pos(self, value: float) -> None:
        self._thumb_pos = value
        self.update()

    thumbPos = Property(float, _get_thumb_pos, _set_thumb_pos)  # type: ignore[arg-type]

    def _on_toggled(self, checked: bool) -> None:
        if self._anim is not None:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"thumbPos", self)
        self._anim.setDuration(150)
        self._anim.setStartValue(self._thumb_pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        t = get_tokens()
        w, h = self.width(), self.height()
        track_radius = h / 2  # 11
        thumb_d = 16
        margin = 3

        # Interpolate track colour between OFF / ON based on thumb position
        off_color = QColor(t.border_primary)
        on_color = QColor(t.accent)
        track_color = _lerp_color(off_color, on_color, self._thumb_pos)

        # Track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(QRectF(0, 0, w, h), track_radius, track_radius)

        # Thumb position
        thumb_x = margin + (w - thumb_d - margin * 2) * self._thumb_pos
        thumb_y = (h - thumb_d) / 2

        # Thumb shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 30)))
        p.drawEllipse(QRectF(thumb_x + 1, thumb_y + 1, thumb_d, thumb_d))

        # Thumb
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(QPen(QColor(0, 0, 0, 20), 0.5))
        p.drawEllipse(QRectF(thumb_x, thumb_y, thumb_d, thumb_d))

        p.end()

    # ------------------------------------------------------------------
    # Size hint
    # ------------------------------------------------------------------

    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(40, 22)


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    """Linear interpolation between two QColors."""
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )
