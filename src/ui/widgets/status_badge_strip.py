"""Status badge strip — clickable status-count badges for quick filtering."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ...models.repository import TaskRepository
from ...models.task_filter import TaskFilter, SortCriterion
from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens

STATUS_ORDER = [
    (TaskStatus.OVERDUE, "逾期"),
    (TaskStatus.TODO, "待办"),
    (TaskStatus.DOING, "进行中"),
    (TaskStatus.DONE, "已完成"),
]


class _StatBadge(QPushButton):
    clicked = Signal()

    def __init__(self, text: str = "", color: str = "#999") -> None:
        super().__init__(text)
        self._color = color
        self._active = False
        self.setObjectName("statusBadge")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        font = self.font()
        font.setPointSize(10)
        self.setFont(font)
        self._render()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._render()

    def _render(self) -> None:
        t = get_tokens()
        if self._active:
            bg = self._color
            fg = t.text_on_accent
            bd = self._color
        else:
            bg = t.bg_tertiary
            fg = self._color
            bd = f"{self._color}55"
        self.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {fg}; border: 1.5px solid {bd}; "
            f"border-radius: 12px; padding: 3px 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ border-color: {self._color}; }}"
        )

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class StatusBadgeStrip(QWidget):
    """Row of clickable status-count badges that emit a filter on click."""

    filter_changed = Signal(TaskFilter)

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._partition_id: str | None = None
        self._badges: dict[TaskStatus, _StatBadge] = {}
        self._active_status: TaskStatus | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        for status, label in STATUS_ORDER:
            badge = _StatBadge("0", status.display_color)
            badge.clicked.connect(lambda s=status: self._on_badge_clicked(s))
            self._badges[status] = badge
            layout.addWidget(badge)

        layout.addStretch()

    def refresh_theme(self) -> None:
        """Re-render all badges with current theme colours."""
        for badge in self._badges.values():
            badge._render()

    def set_partition_id(self, pid: str | None) -> None:
        self._partition_id = pid

    def refresh(self, date_from=None, date_to=None) -> None:
        counts = self._repository.get_status_counts(
            self._partition_id, date_from=date_from, date_to=date_to
        )
        for status, badge in self._badges.items():
            cnt = counts.get(status, 0)
            badge.setText(f"{status.display_name} {cnt}")

    def _on_badge_clicked(self, status: TaskStatus) -> None:
        if self._active_status == status:
            self._active_status = None
            for b in self._badges.values():
                b.set_active(False)
            filter_ = TaskFilter(
                partition_id=self._partition_id,
                sort_by=[SortCriterion("urgency", ascending=True)],
            )
        else:
            self._active_status = status
            for s, b in self._badges.items():
                b.set_active(s == status)
            filter_ = TaskFilter(
                statuses={status},
                partition_id=self._partition_id,
                sort_by=[SortCriterion("urgency", ascending=True)],
            )
        self.filter_changed.emit(filter_)
