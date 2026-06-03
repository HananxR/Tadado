"""Custom delegate for rendering urgency row strip, status badges, and red-bold text."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QStyledItemDelegate

from ...models.task import Task
from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens


class TaskListDelegate(QStyledItemDelegate):
    """Paints urgency left-edge strip, status badges, and red-bold highlight text."""

    _BADGE_PADDING_H = 8
    _BADGE_PADDING_V = 3
    _BADGE_RADIUS = 4

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        col = index.column()
        task: Task | None = index.data(Qt.ItemDataRole.UserRole)

        # Checkbox column — custom large checkmark
        if col == 0:
            painter.save()
            # Background
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            else:
                t0 = get_tokens()
                bg = QColor(t0.bg_secondary)
                bg.setAlpha(20)
                painter.fillRect(option.rect, bg)
            # Draw checkmark
            checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
            rect = option.rect
            cx = rect.center().x()
            cy = rect.center().y()
            size = 18
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if checked:
                t = get_tokens()
                painter.setBrush(QColor(t.success))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(cx, cy), size / 2, size / 2)
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawLine(
                    QPointF(cx - size * 0.22, cy),
                    QPointF(cx - size * 0.05, cy + size * 0.22)
                )
                painter.drawLine(
                    QPointF(cx - size * 0.05, cy + size * 0.22),
                    QPointF(cx + size * 0.28, cy - size * 0.18)
                )
            else:
                t2 = get_tokens()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(t2.text_secondary), 2))
                painter.drawEllipse(QPointF(cx, cy), size / 2, size / 2)
            painter.restore()
            return

        if task is None:
            super().paint(painter, option, index)
            return

        # Dim suspended tasks
        if task.suspended:
            painter.save()
            painter.setOpacity(0.45)
            super().paint(painter, option, index)
            painter.restore()
            return

        # Draw urgency row background for all non-checkbox columns (skip if red-bold highlighted)
        model = index.model()
        hl_id = model.highlighted_task_id() if model else None
        is_highlighted = hl_id is not None and task.id == hl_id
        if not is_highlighted:
            self._draw_urgency_bg(painter, option, task)

        if col == 6:  # COL_STATUS — custom badge painting
            self._paint_status_badge(painter, option, task)
        elif col == 8:  # COL_ARCHIVED — colored text
            self._paint_archived(painter, option, task)
        elif col == 3:  # COL_CONTENT — red bold text for highlighted task
            fg = index.data(Qt.ItemDataRole.ForegroundRole)
            font = index.data(Qt.ItemDataRole.FontRole)
            if fg is not None and font is not None:
                painter.save()
                painter.setPen(QPen(fg))
                painter.setFont(font)
                text = index.data(Qt.ItemDataRole.DisplayRole)
                painter.drawText(option.rect.adjusted(4, 1, -4, -1),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
                painter.restore()
                return
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.StateFlag.State_Selected
            super().paint(painter, opt, index)
        else:
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.StateFlag.State_Selected
            super().paint(painter, opt, index)

    def editorEvent(self, event, model, option, index) -> bool:
        """Handle checkbox toggle on mouse click."""
        if index.column() == 0 and event.type() == event.Type.MouseButtonRelease:
            checked = index.data(Qt.ItemDataRole.CheckStateRole)
            model.setData(index, Qt.CheckState.Unchecked if checked == Qt.CheckState.Checked else Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(super().sizeHint(option, index).width(), 30)

    # ------------------------------------------------------------------
    # Urgency row background
    # ------------------------------------------------------------------

    def _draw_urgency_bg(
        self, painter: QPainter, option: QStyleOptionViewItem, task: Task
    ) -> None:
        """Draw a full-row urgency background tint, unless the task is highlighted (red bold)."""
        # Skip if this is the highlighted (red bold) task
        from ...utils.design_tokens import is_dark
        urgency = getattr(task, 'urgency', 3)

        t = get_tokens()
        color_map = {
            0: QColor(t.urgency_urgent),
            1: QColor(t.urgency_high),
            2: QColor(t.urgency_medium),
            3: QColor(t.urgency_normal),
        }
        color = color_map.get(urgency, QColor(t.urgency_normal))
        alpha = 50 if is_dark() else 35
        color.setAlpha(alpha)

        painter.save()
        painter.fillRect(option.rect, color)
        painter.restore()

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
    # Archived column
    # ------------------------------------------------------------------

    def _paint_archived(
        self, painter: QPainter, option: QStyleOptionViewItem, task: Task
    ) -> None:
        if task.status != TaskStatus.DONE:
            text = "/"
            t = get_tokens()
            color = QColor(t.text_disabled)
        elif task.archived:
            text = "已归档"
            t = get_tokens()
            color = QColor(t.success)
        else:
            text = "未归档"
            t = get_tokens()
            color = QColor("#e67e22")  # orange

        painter.save()
        painter.setPen(color)
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()
