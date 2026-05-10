"""Custom delegate for rendering status badges and priority indicators."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyleOptionViewItem, QStyledItemDelegate


class TaskListDelegate(QStyledItemDelegate):
    """Paints status as a colored rounded badge, priority as colored text."""

    _BADGE_PADDING_H = 6
    _BADGE_PADDING_V = 2
    _BADGE_RADIUS = 3

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        col = index.column()

        if col == 1:
            self._paint_status_badge(painter, option, index)
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(base.height(), 28))

    # ------------------------------------------------------------------
    # Status badge
    # ------------------------------------------------------------------

    def _paint_status_badge(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color_name = self._status_color(index)

        painter.save()

        # Background highlight
        if option.state & QStyleOptionViewItem.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        color = QColor(color_name)
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        badge_w = text_width + self._BADGE_PADDING_H * 2
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

        # Text — white on dark badges, dark on light
        lum = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        text_color = QColor(255, 255, 255) if lum < 128 else QColor(51, 51, 51)
        painter.setPen(text_color)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()

    @staticmethod
    def _status_color(index: QModelIndex) -> str:
        task = index.data(Qt.ItemDataRole.UserRole)
        if task is not None:
            return task.status.display_color
        return "#999"
