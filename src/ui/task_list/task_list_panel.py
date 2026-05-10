"""Composed task list panel: input + filter bar + table view."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_filter import SortCriterion, TaskFilter
from ...models.task_status import TaskStatus
from ...utils.signal_bus import get_signal_bus
from ..widgets.filter_bar import FilterBar
from ..widgets.task_input import TaskInputWidget
from .task_list_model import TaskListModel
from .task_list_view import TaskListView


class TaskListPanel(QWidget):
    """Complete task list panel — input, filter, and table view."""

    date_filter_applied = Signal(date)

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._current_filter = TaskFilter()

        self.setObjectName("taskListPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Input
        self._input = TaskInputWidget(repository)
        self._input.setFixedHeight(36)
        layout.addWidget(self._input)

        # Filter
        self._filter_bar = FilterBar()
        layout.addWidget(self._filter_bar)

        # View
        self._model = TaskListModel()
        self._view = TaskListView(repository)
        self._view.set_model(self._model)
        layout.addWidget(self._view, 1)

        # Connections
        self._filter_bar.filter_changed.connect(self._on_filter_changed)
        self._signal_bus.task_created.connect(self._on_task_created)
        self._signal_bus.task_updated.connect(self._on_task_updated)
        self._signal_bus.task_deleted.connect(self._on_task_deleted)
        self._signal_bus.task_status_changed.connect(self._on_task_updated)
        self._signal_bus.scan_completed.connect(self._on_data_changed)

        # Initial load
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        tasks = self._repository.search(self._current_filter)
        self._model.load_tasks(tasks)

    def apply_preset_filter(self, preset: str) -> None:
        today = date.today()

        if preset == "all":
            self._current_filter = TaskFilter()
            self._filter_bar.reset()
        elif preset == "today":
            self._current_filter = TaskFilter(
                date_from=today, date_to=today, overdue_only=True
            )
        elif preset == "week":
            weekday = today.isoweekday()
            monday = today - timedelta(days=weekday - 1)
            sunday = monday + timedelta(days=6)
            self._current_filter = TaskFilter(date_from=monday, date_to=sunday)
        elif preset == "overdue":
            self._current_filter = TaskFilter(overdue_only=True)

        self.refresh()

    def apply_date_filter(self, d: date) -> None:
        self._current_filter = TaskFilter(date_from=d, date_to=d)
        self._filter_bar.reset()
        self._filter_bar.blockSignals(True)
        self._filter_bar.blockSignals(False)
        self.refresh()

    def set_sort(self, field: str, ascending: bool = True) -> None:
        self._current_filter.sort_by = [SortCriterion(field=field, ascending=ascending)]
        self.refresh()

    @property
    def task_list_view(self) -> TaskListView:
        return self._view

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_filter_changed(self, filter_: TaskFilter) -> None:
        self._current_filter = filter_
        self.refresh()

    def _on_task_created(self, task: Task) -> None:
        self.refresh()

    def _on_task_updated(self, task: Task) -> None:
        self.refresh()

    def _on_task_deleted(self, task_id: str) -> None:
        self.refresh()

    def _on_data_changed(self, *args) -> None:
        self.refresh()
