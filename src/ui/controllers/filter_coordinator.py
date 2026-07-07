"""FilterCoordinator — data refresh core, filter merge, pagination, task selection."""

from __future__ import annotations

import logging
from datetime import date as _date

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLabel

from ...config import AppConfig
from ...models.task_filter import SortCriterion, TaskFilter
from ...services.task_service import TaskService

_log = logging.getLogger("runlog")


class FilterCoordinator(QObject):
    """Coordinates data refresh for the main edit view.

    Owns filter merging, pagination state, task selection/highlight,
    and new-task sort handling.  All widget signal connections happen
    internally.

    Signals:
        status_message(msg): emitted for status-bar flash messages
    """

    status_message = Signal(str)

    def __init__(
        self,
        task_service: TaskService,
        filter_bar,  # FilterBar
        quick_overview,  # QuickOverviewBar
        task_model,  # TaskListModel
        task_view,  # TaskListView
        progress_bar,  # ProgressDynamicsBar
        status_badge,  # StatusBadgeStrip
        edit_panel,  # TaskEditPanel
        status_msg_label: QLabel,
        config: AppConfig,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = task_service
        self._filter_bar = filter_bar
        self._quick_overview = quick_overview
        self._task_model = task_model
        self._task_view = task_view
        self._progress_bar = progress_bar
        self._status_badge = status_badge
        self._edit_panel = edit_panel
        self._status_msg = status_msg_label
        self._config = config

        # State
        self._page = 0
        self._page_size = 20
        self._total_count = 0
        self._carousel_filter: TaskFilter | None = None
        self._new_task_sort_active = False
        self._setting_sort_internally = False
        self._selection_guard = False
        self._partition_id: str | None = None
        self._progress_active = False  # True when progress bar button is clicked

        # Wire widget signals
        self._filter_bar.filter_changed.connect(self._on_filter_changed)
        self._quick_overview.preset_activated.connect(self._on_quick_preset)
        self._quick_overview.task_clicked.connect(self._on_carousel_clicked)
        self._progress_bar.task_clicked.connect(self._on_carousel_clicked)
        self._progress_bar.progress_filter_activated.connect(self._on_progress_filter)
        self._status_badge.filter_changed.connect(self._on_filter_changed)
        self._task_view.task_selected.connect(self._on_view_task_selected)
        self._task_view.detail_requested.connect(
            lambda task: self._edit_panel.load_task(task)
        )
        self._task_model.dataChanged.connect(self._on_model_data_changed)

    # ------------------------------------------------------------------
    # Public API — called from MainWindow
    # ------------------------------------------------------------------

    def refresh(self, partition_id: str | None = None) -> None:
        """Refresh all views for a partition (or current state)."""
        if partition_id is not None:
            self._partition_id = partition_id
        self._refresh_all_views()

    def build_filter(self) -> TaskFilter:
        """Merge filter bar + quick_overview + carousel + partition into one filter."""
        f = self._filter_bar.build_filter()
        if self._carousel_filter:
            if self._carousel_filter.date_from:
                f.date_from = self._carousel_filter.date_from
            if self._carousel_filter.date_to:
                f.date_to = self._carousel_filter.date_to
            if self._carousel_filter.overdue_only:
                f.overdue_only = True
            if self._carousel_filter.activity_field:
                f.activity_field = self._carousel_filter.activity_field
                f.activity_min = self._carousel_filter.activity_min
        f.partition_id = (
            self._carousel_filter.partition_id
            if self._carousel_filter
            else None
        ) or self._partition_id or None
        if not f.sort_by:
            f.sort_by = [SortCriterion("deadline", ascending=True)]
        return f

    def handle_new_task_sort(self) -> None:
        """Activate new-task sort mode (sort by created_at desc)."""
        self._new_task_sort_active = True
        self._progress_active = False
        self._progress_bar.reset_to_unclicked()
        self._carousel_filter = self._quick_overview.build_filter()
        self._filter_bar.set_sort("created")
        self._filter_bar.reset()
        self.refresh()

    def handle_tasks_bulk_created(self, count: int, task_ids: list[str]) -> None:
        """Handle bulk-created tasks — switch to today filter, select first."""
        self._quick_overview.activate_preset("today")
        self._progress_active = False
        self._progress_bar.reset_to_unclicked()
        self._new_task_sort_active = True
        self._filter_bar.set_sort("created")
        self._filter_bar.reset()
        self.refresh()
        # Select first task
        if task_ids and self._task_model.rowCount() > 0:
            self._select_task_by_id(task_ids[0])

    def go_home(self) -> None:
        """Reset to edit view home state."""
        self._quick_overview.activate_preset("today")
        self._carousel_filter = None
        self._progress_active = False
        self._progress_bar.reset_to_unclicked()
        self._filter_bar.reset()
        self._page = 0
        self.refresh()
        if self._task_model.rowCount() > 0:
            self._on_task_selected(self._task_model.tasks[0])

    def set_page_size(self, size: int) -> None:
        """Update page size and re-query."""
        self._page_size = size
        self._page = 0
        self._refresh_all_views()

    def set_partition(self, pid: str) -> None:
        """Set partition context for filter building."""
        self._partition_id = pid

    @property
    def page_size(self) -> int:
        return self._page_size

    # ------------------------------------------------------------------
    # Internal — data refresh
    # ------------------------------------------------------------------

    def _refresh_all_views(self) -> None:
        """Query tasks and update all views."""
        f = self.build_filter()
        f.limit = self._page_size
        f.offset = self._page * self._page_size
        # Progress bar active → main list also shows archived tasks
        if self._progress_active:
            f.show_archived = True

        tasks, self._total_count = self._svc.search_with_total(f)
        self._task_model.load_tasks(tasks)
        # Get unpaginated list for quick overview / progress bar (includes archived)
        f.limit = None
        f.offset = 0
        f.show_archived = True
        all_tasks = self._svc.search(f)
        self._quick_overview.set_items(all_tasks)
        self._quick_overview.set_partition_id(self._partition_id)
        self._update_page_label()
        self._update_status_bar()
        self._status_badge.refresh()
        self._progress_bar.set_items(all_tasks)

    def _update_page_label(self) -> None:
        # Handled externally via page buttons — no direct label here.
        # The pagination label is in MainWindow.
        pass

    def _update_status_bar(self) -> None:
        """Update status bar with partition counts."""
        counts = self._svc.get_status_counts(partition_id=self._partition_id)
        parts = []
        for status, label in [
            ("OVERDUE", "逾期"),
            ("DOING", "进行中"),
            ("TODO", "待办"),
            ("DONE", "已完成"),
        ]:
            for s, c in counts.items():
                if s.value == status:
                    parts.append(f"{label} {c}")
                    break
        total = sum(counts.values())
        parts.append(f"共{total}项")
        self._status_msg.setText(" | ".join(p for p in parts if p))

    # ------------------------------------------------------------------
    # Internal — task selection
    # ------------------------------------------------------------------

    def _on_view_task_selected(self, task) -> None:
        if self._selection_guard:
            return
        self._on_task_selected(task)

    def _on_task_selected(self, task) -> None:
        """Highlight task in list and load into editor."""
        self._task_model.set_highlighted_task(task.id)
        self._edit_panel.load_task(task)
        # Select row in table
        for row in range(self._task_model.rowCount()):
            idx = self._task_model.index(row, 1)
            if idx.data() == task.id:
                self._selection_guard = True
                self._task_view.selectRow(row)
                self._task_view.scrollTo(idx)
                self._selection_guard = False
                break

    def _select_task_by_id(self, task_id: str) -> None:
        for task in self._task_model.tasks:
            if task.id == task_id:
                self._on_task_selected(task)
                return

    def _on_carousel_clicked(self, task_id: str) -> None:
        self._select_task_by_id(task_id)

    # ------------------------------------------------------------------
    # Internal — filter slots
    # ------------------------------------------------------------------

    def _on_filter_changed(self, filter_: TaskFilter) -> None:
        if not self._setting_sort_internally:
            self._new_task_sort_active = False
        self._carousel_filter = filter_
        self._progress_active = False
        self._progress_bar.reset_to_unclicked()
        self._refresh_all_views()
        if self._task_model.rowCount() > 0:
            self._on_task_selected(self._task_model.tasks[0])

    def _on_quick_preset(self, preset: str) -> None:
        self._new_task_sort_active = False
        self._progress_active = False
        self._carousel_filter = self._quick_overview.build_filter()
        self._progress_bar.reset_to_unclicked()
        self._refresh_all_views()
        if self._task_model.rowCount() > 0:
            self._on_task_selected(self._task_model.tasks[0])

    def _on_progress_filter(self, filter_: TaskFilter) -> None:
        self._progress_active = True
        self._carousel_filter = filter_
        self._refresh_all_views()
        self._update_page_label()
        if self._task_model.rowCount() > 0:
            self._on_task_selected(self._task_model.tasks[0])

    def _on_model_data_changed(self) -> None:
        # Propagate model changes to toolbar
        pass  # MainWindow connects toolbar to model in central_widget
