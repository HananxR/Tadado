"""Custom delegate for rendering status badges and urgency row backgrounds."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QStyledItemDelegate

from ...models.task import Task
from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens


class TaskListDelegate(QStyledItemDelegate):
    """Paints status as a colored rounded badge and urgency-tinted row backgrounds."""

    _BADGE_PADDING_H = 8
    _BADGE_PADDING_V = 3
    _BADGE_RADIUS = 4

    # Color stops for urgency tint: cool (t=0, far future) → warm (t=1, severely overdue)
    _COLOR_STOPS: list[tuple[float, tuple[int, int, int]]] = [
        (0.0, (200, 210, 220)),   # cool gray-blue
        (0.2, (52, 152, 219)),    # blue
        (0.4, (241, 196, 15)),    # amber
        (0.6, (230, 126, 34)),    # orange
        (0.85, (231, 76, 60)),    # red
        (1.0, (192, 30, 30)),     # deep red (severely overdue)
    ]

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
                # Draw checkmark ✓
                painter.drawLine(
                    QPointF(cx - size * 0.22, cy),
                    QPointF(cx - size * 0.05, cy + size * 0.22)
                )
                painter.drawLine(
                    QPointF(cx - size * 0.05, cy + size * 0.22),
                    QPointF(cx + size * 0.28, cy - size * 0.18)
                )
            else:
                # Empty circle outline — use text_secondary for better visibility
                t2 = get_tokens()
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(t2.text_secondary), 2))
                painter.drawEllipse(QPointF(cx, cy), size / 2, size / 2)
            painter.restore()
            return

        if task is None:
            super().paint(painter, option, index)
            return

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # Dim suspended tasks
        if task.suspended:
            painter.save()
            painter.setOpacity(0.45)
            super().paint(painter, option, index)
            painter.restore()
            return

        if col == 6:  # COL_STATUS — custom badge painting
            if not is_selected:
                bg = self._urgency_bg_color(task)
                if bg is not None:
                    painter.save()
                    painter.fillRect(option.rect, bg)
                    painter.restore()
            self._paint_status_badge(painter, option, task)
        elif col == 8:  # COL_ARCHIVED — colored text
            if not is_selected:
                bg = self._urgency_bg_color(task)
                if bg is not None:
                    painter.save()
                    painter.fillRect(option.rect, bg)
                    painter.restore()
            self._paint_archived(painter, option, task)
        else:
            if not is_selected:
                bg = self._urgency_bg_color(task)
                if bg is not None:
                    painter.save()
                    painter.fillRect(option.rect, bg)
                    painter.restore()
            # Suppress system selection background
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.StateFlag.State_Selected
            # Highlighted task: red bold text only, no background change
            # Urgency bg already drawn above; grid lines drawn by QTableView after delegate
            if col == 3:
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
            super().paint(painter, opt, index)
            # Suppress system selection background — red+bold is the sole indicator
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
    # Urgency background
    # ------------------------------------------------------------------

    @staticmethod
    def _urgency_bg_color(task: Task) -> QColor | None:
        """Map task urgency_score to a warm→cool background tint overlay."""
        score = task.urgency_score

        if score <= -9998:  # no deadline
            return None
        if score <= -9990:  # DONE
            t3 = get_tokens()
            c = QColor(t3.success)
            c.setAlpha(12)
            return c

        clamped = max(-30.0, min(30.0, score))
        t = (clamped + 30.0) / 60.0  # normalize to [0, 1]

        r, g, b = TaskListDelegate._interpolate_color(TaskListDelegate._COLOR_STOPS, t)
        # Bold alpha: cool/far → hot/urgent (higher in dark mode for visibility)
        from ...utils.design_tokens import is_dark
        alpha = int(150 + t * 105) if is_dark() else int(100 + t * 100)
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
