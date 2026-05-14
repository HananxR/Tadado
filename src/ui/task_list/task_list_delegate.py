"""Custom delegate for rendering status badges and priority indicators."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QStyledItemDelegate

from ...models.priority import Priority
from ...models.task import Task


class TaskListDelegate(QStyledItemDelegate):
    """Paints status as a colored rounded badge, priority as colored dot + label."""

    _BADGE_PADDING_H = 8
    _BADGE_PADDING_V = 3
    _BADGE_RADIUS = 4

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        col = index.column()
        task: Task | None = index.data(Qt.ItemDataRole.UserRole)
        if task is None:
            super().paint(painter, option, index)
            return

        if col == 5:  # COL_STATUS
            self._paint_status_badge(painter, option, task)
        elif col == 4:  # COL_PRIORITY
            self._paint_priority_indicator(painter, option, task)
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(base.height(), 28))

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

    # ------------------------------------------------------------------
    # Priority indicator
    # ------------------------------------------------------------------

    def _paint_priority_indicator(
        self, painter: QPainter, option: QStyleOptionViewItem, task: Task
    ) -> None:
        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        if task.priority == Priority.NONE:
            # Show a subtle dash for no priority
            painter.setPen(QColor(200, 200, 200))
            fm = painter.fontMetrics()
            painter.drawText(
                QRectF(option.rect),
                Qt.AlignmentFlag.AlignCenter,
                "—",
            )
            painter.restore()
            return

        text = task.priority.name
        color = QColor(task.priority.display_color)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        dot_size = fm.height() - 4
        total_w = dot_size + 4 + text_w
        start_x = option.rect.center().x() - total_w // 2

        # Colored dot
        dot_rect = QRectF(
            float(start_x),
            float(option.rect.center().y()) - dot_size / 2.0,
            float(dot_size),
            float(dot_size),
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(dot_rect)

        # Priority label
        painter.setPen(
            color
            if not (option.state & QStyle.StateFlag.State_Selected)
            else QColor(51, 51, 51)
        )
        painter.drawText(
            QRectF(
                float(start_x + dot_size + 4),
                float(option.rect.y()),
                float(text_w + 4),
                float(option.rect.height()),
            ),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

        painter.restore()
