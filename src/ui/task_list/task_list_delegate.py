"""Custom delegate for rendering status badges and urgency row backgrounds."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QStyledItemDelegate

from ...models.task import Task
from ...models.task_status import TaskStatus


class TaskListDelegate(QStyledItemDelegate):
    """Paints status as a colored rounded badge and urgency-tinted row backgrounds."""

    _BADGE_PADDING_H = 8
    _BADGE_PADDING_V = 3
    _BADGE_RADIUS = 4

    # Color stops for urgency tint: cool (t=0, far future) → warm (t=1, severely overdue)
    _COLOR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
        (0.0, (236, 240, 241)),   # pale gray-blue
        (0.3, (52, 152, 219)),    # blue
        (0.5, (241, 196, 15)),    # amber
        (0.7, (230, 126, 34)),    # orange
        (1.0, (231, 76, 60)),     # red
    ]

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        col = index.column()
        task: Task | None = index.data(Qt.ItemDataRole.UserRole)
        if task is None:
            super().paint(painter, option, index)
            return

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if col == 5:  # COL_STATUS — custom badge painting
            if not is_selected:
                bg = self._urgency_bg_color(task)
                if bg is not None:
                    painter.save()
                    painter.fillRect(option.rect, bg)
                    painter.restore()
            self._paint_status_badge(painter, option, task)
        else:
            super().paint(painter, option, index)
            # Overlay urgency tint on top (after QSS rendering) so it's always visible
            if not is_selected:
                bg = self._urgency_bg_color(task)
                if bg is not None:
                    painter.save()
                    painter.fillRect(option.rect, bg)
                    painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(base.height(), 28))

    # ------------------------------------------------------------------
    # Urgency background
    # ------------------------------------------------------------------

    @staticmethod
    def _urgency_bg_color(task: Task) -> QColor | None:
        """Map task urgency_score to a warm→cool background tint overlay."""
        score = task.urgency_score

        if score <= -9998:  # no deadline
            return None
        if score <= -9990:  # DONE
            return QColor(46, 204, 113, 12)

        clamped = max(-30.0, min(30.0, score))
        t = (clamped + 30.0) / 60.0  # normalize to [0, 1]

        r, g, b = TaskListDelegate._interpolate_color(TaskListDelegate._COLOR_STOPS, t)
        # Higher alpha for overlay approach: 10 (cool/far) → 45 (hot/urgent)
        alpha = int(10 + t * 35)
        return QColor(r, g, b, alpha)

    @staticmethod
    def _interpolate_color(
        stops: list[tuple[float, tuple[int, int, int]]], t: float
    ) -> tuple[int, int, int]:
        """Linear interpolation between color stops."""
        if t <= stops[0][0]:
            return stops[0][1]
        if t >= stops[-1][0]:
            return stops[-1][1]

        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                ratio = (t - t0) / (t1 - t0)
                return (
                    int(c0[0] + (c1[0] - c0[0]) * ratio),
                    int(c0[1] + (c1[1] - c0[1]) * ratio),
                    int(c0[2] + (c1[2] - c0[2]) * ratio),
                )

        return stops[-1][1]

    # ------------------------------------------------------------------
    # Status badge
    # ------------------------------------------------------------------

    def _paint_status_badge(
        self, painter: QPainter, option: QStyleOptionViewItem, task: Task
    ) -> None:
        text = task.status.display_name
        color = QColor(task.status.display_color)

        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        badge_w = text_w + self._BADGE_PADDING_H * 2
        badge_h = fm.height() + self._BADGE_PADDING_V * 2

        badge_rect = QRectF(
            float(option.rect.center().x()) - badge_w / 2.0,
            float(option.rect.center().y()) - badge_h / 2.0,
            badge_w,
            badge_h,
        )

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, self._BADGE_RADIUS, self._BADGE_RADIUS)

        lum = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        text_color = QColor(255, 255, 255) if lum < 128 else QColor(51, 51, 51)
        painter.setPen(text_color)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()
