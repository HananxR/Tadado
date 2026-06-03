"""Horizontal filter bar with search, status, and sort controls."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget,
)

from ...models.task_filter import SortCriterion, TaskFilter
from ...models.task_status import TaskStatus

from ...utils.widget_utils import combo_width

from .dropdown import DropdownWidget


class FilterBar(QWidget):
    """Combo-based filter bar that emits a TaskFilter on any change."""

    filter_changed = Signal(TaskFilter)

    _SORT_MAP: dict[str, str] = {
        "优先级": "urgency",
        "截止日": "deadline",
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

        # Status combo — compact fixed width (longest item "进行中" ≈ 3 chars)
        self._status = DropdownWidget()
        self._status.setObjectName("statusFilter")
        self._status.addItem("状态", None)
        for s in (TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE, TaskStatus.OVERDUE):
            self._status.addItem(s.display_name, s)
        self._status.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self._status)

        # Sort combo — compact fixed width (longest item "创建时间" ≈ 4 chars)
        sort_label = QLabel("排序：")
        sort_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(sort_label)
        self._sort = DropdownWidget()
        self._sort.setObjectName("sortCombo")
        for label in self._SORT_MAP:
            self._sort.addItem(label)
        self._sort.setCurrentIndex(0)  # default: 优先级
        self._sort.setFixedWidth(combo_width(4))
        self._sort.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._sort.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self._sort)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_filter(self) -> TaskFilter:
        f = TaskFilter()
        f.search_text = self._search.text().strip()

        status_data = self._status.currentData()
        if status_data is not None:
            f.statuses = {status_data}

        sort_label = self._sort.currentText()
        field = self._SORT_MAP.get(sort_label, "deadline")
        f.sort_by = [SortCriterion(field=field, ascending=True)]

        return f

    def reset(self) -> None:
        self._search.clear()
        self._status.setCurrentIndex(0)

    def set_sort(self, field: str) -> None:
        """Set the sort combo to the given field name (e.g. 'status', 'deadline')."""
        for display, key in self._SORT_MAP.items():
            if key == field:
                idx = self._sort.findText(display)
                if idx >= 0:
                    self._sort.setCurrentIndex(idx)
                return

    def set_preset(self, preset: str) -> None:
        self.reset()
        if preset == "today":
            self._status.setCurrentIndex(0)
            pass  # priority removed
        elif preset == "week":
            self._status.setCurrentIndex(0)
            pass  # priority removed
        elif preset == "overdue":
            self._status.setCurrentIndex(0)
            pass  # priority removed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        self.filter_changed.emit(self.build_filter())
