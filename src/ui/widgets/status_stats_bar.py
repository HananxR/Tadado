"""Status statistics bar — clickable status counts with day/week/month/year toggles."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ...models.repository import TaskRepository
from ...models.task_filter import SortCriterion, TaskFilter
from ...models.task_status import TaskStatus


class _StatBadge(QLabel):
    """A single clickable statistic pill."""

    clicked = Signal()

    def __init__(self, text: str, color: str = "#888", active: bool = False) -> None:
        super().__init__(text)
        self._color = color
        self._active = active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def _update_style(self) -> None:
        bg = self._color if self._active else "transparent"
        text_c = "#fff" if self._active else self._color
        border = self._color if self._active else "#ddd"
        self.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {text_c}; border: 1px solid {border};"
            f" border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: bold; }}"
        )

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()


class StatusStatsBar(QWidget):
    """Horizontal bar showing URGENT/TODO/DOING/DONE counts aggregated by period.

    Clicking a status badge filters the task list.
    Clicking a period (日/周/月/年) changes the aggregation.
    """

    filter_changed = Signal(TaskFilter)

    _STATUSES = [
        (TaskStatus.URGENT, "#e74c3c", "紧急"),
        (TaskStatus.TODO, "#5b8def", "待办"),
        (TaskStatus.DOING, "#f39c12", "进行中"),
        (TaskStatus.DONE, "#27ae60", "已完成"),
    ]
    _PERIODS = [("日", "day"), ("周", "week"), ("月", "month"), ("年", "year")]

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._active_status: TaskStatus | None = None
        self._active_period: str = "day"
        self._active_partition_id: str | None = None
        self._badges: dict[TaskStatus, _StatBadge] = {}
        self._period_labels: dict[str, QLabel] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        # Status badges
        for status, color, label in self._STATUSES:
            badge = _StatBadge(f"{label}: 0", color)
            badge.clicked.connect(lambda s=status: self._on_status_clicked(s))
            self._badges[status] = badge
            layout.addWidget(badge)

        layout.addStretch()

        # Period toggles
        for label, key in self._PERIODS:
            lbl = QLabel(label)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.setStyleSheet(
                "QLabel { color: #aaa; font-size: 10px; padding: 1px 6px; }"
            )
            lbl.mousePressEvent = lambda e, k=key: self._on_period_clicked(k)
            self._period_labels[key] = lbl
            layout.addWidget(lbl)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_partition_id(self, partition_id: str | None) -> None:
        """Set the active partition scope for stats and filtering."""
        self._active_partition_id = partition_id

    def get_counts(self) -> dict[TaskStatus, int]:
        """Return the last-refreshed status counts."""
        counts = {}
        for status in (TaskStatus.URGENT, TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            badge = self._badges.get(status)
            if badge:
                text = badge.text()
                parts = text.split(": ")
                counts[status] = int(parts[1]) if len(parts) > 1 else 0
        return counts

    def refresh(self, date_from: date | None = None, date_to: date | None = None,
                overdue_only: bool = False) -> None:
        if date_from is not None and date_to is not None:
            start, end = date_from, date_to
        else:
            today = date.today()
            if self._active_period == "day":
                start = today
                end = today
            elif self._active_period == "week":
                weekday = today.isoweekday()
                start = today - timedelta(days=weekday - 1)
                end = start + timedelta(days=6)
            elif self._active_period == "month":
                start = today.replace(day=1)
                if today.month == 12:
                    end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
            else:  # year
                start = today.replace(month=1, day=1)
                end = today.replace(month=12, day=31)

        for status, color, label in self._STATUSES:
            f = TaskFilter(statuses={status}, date_from=start, date_to=end)
            if self._active_partition_id:
                f.partition_id = self._active_partition_id
            if overdue_only:
                f.overdue_only = True
            count = self._repository.count(f)
            badge = self._badges[status]
            badge.setText(f"{label}: {count}")
            badge.set_active(status == self._active_status)

        for key, lbl in self._period_labels.items():
            active = key == self._active_period
            lbl.setStyleSheet(
                f"QLabel {{ color: {'#333' if active else '#aaa'};"
                f" font-size: 10px; padding: 1px 6px;"
                f" font-weight: {'bold' if active else 'normal'}; }}"
            )

    def _build_filter(self) -> TaskFilter:
        today = date.today()
        if self._active_period == "day":
            start, end = today, today
        elif self._active_period == "week":
            wd = today.isoweekday()
            start = today - timedelta(days=wd - 1)
            end = start + timedelta(days=6)
        elif self._active_period == "month":
            start = today.replace(day=1)
            if today.month == 12:
                end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        else:
            start = today.replace(month=1, day=1)
            end = today.replace(month=12, day=31)

        f = TaskFilter(date_from=start, date_to=end)
        if self._active_status is not None:
            f.statuses = {self._active_status}
        if self._active_partition_id:
            f.partition_id = self._active_partition_id
        f.sort_by = [SortCriterion(field="deadline", ascending=True)]
        return f

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_status_clicked(self, status: TaskStatus) -> None:
        if self._active_status == status:
            self._active_status = None
        else:
            self._active_status = status
        self.refresh()
        self.filter_changed.emit(self._build_filter())

    def _on_period_clicked(self, period: str) -> None:
        self._active_period = period
        self._active_status = self._active_status  # keep status filter
        self.refresh()
        self.filter_changed.emit(self._build_filter())
