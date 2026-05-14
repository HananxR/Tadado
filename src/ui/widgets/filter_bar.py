"""Horizontal filter bar with search, status, priority, and sort controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget

from ...models.priority import Priority
from ...models.task_filter import SortCriterion, TaskFilter
from ...models.task_status import TaskStatus


class FilterBar(QWidget):
    """Combo-based filter bar that emits a TaskFilter on any change."""

    filter_changed = Signal(TaskFilter)

    _SORT_MAP: dict[str, str] = {
        "截止日": "deadline",
        "优先级": "priority",
        "创建时间": "created",
        "状态": "status",
        "标题": "title",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("filterBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Search input with debounce
        self._search = QLineEdit()
        self._search.setObjectName("searchInput")
        self._search.setPlaceholderText("搜索...")
        self._search.setClearButtonEnabled(True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._on_filter_changed)
        self._search.textChanged.connect(lambda: self._debounce.start())
        layout.addWidget(self._search, 2)

        # Status combo (4 main statuses only)
        self._status = QComboBox()
        self._status.setObjectName("statusFilter")
        self._status.addItem("状态", None)
        for s in (TaskStatus.URGENT, TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            self._status.addItem(s.display_name, s)
        self._status.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self._status, 1)

        # Priority combo (with level mapping)
        self._priority = QComboBox()
        self._priority.setObjectName("priorityFilter")
        self._priority.addItem("优先级", None)
        _PRIORITY_LABELS = {Priority.A: "A (最高)", Priority.B: "B (中等)", Priority.C: "C (低)"}
        for p in (Priority.A, Priority.B, Priority.C):
            self._priority.addItem(_PRIORITY_LABELS.get(p, p.display_tag), p)
        self._priority.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self._priority, 1)

        # Sort combo
        self._sort = QComboBox()
        self._sort.setObjectName("sortCombo")
        for label in self._SORT_MAP:
            self._sort.addItem(label)
        self._sort.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self._sort, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_filter(self) -> TaskFilter:
        f = TaskFilter()
        f.search_text = self._search.text().strip()

        status_data = self._status.currentData()
        if status_data is not None:
            f.statuses = {status_data}

        priority_data = self._priority.currentData()
        if priority_data is not None:
            f.min_priority = priority_data

        sort_label = self._sort.currentText()
        field = self._SORT_MAP.get(sort_label, "deadline")
        f.sort_by = [SortCriterion(field=field, ascending=True)]

        return f

    def reset(self) -> None:
        self._search.clear()
        self._status.setCurrentIndex(0)
        self._priority.setCurrentIndex(0)
        self._sort.setCurrentIndex(0)

    def set_preset(self, preset: str) -> None:
        self.reset()
        if preset == "today":
            self._status.setCurrentIndex(0)
            self._priority.setCurrentIndex(0)
        elif preset == "week":
            self._status.setCurrentIndex(0)
            self._priority.setCurrentIndex(0)
        elif preset == "overdue":
            self._status.setCurrentIndex(0)
            self._priority.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        self.filter_changed.emit(self.build_filter())
