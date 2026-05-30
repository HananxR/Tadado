"""Tag list panel — simple tag selector for activity analysis."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...utils.design_tokens import get_tokens


class TaskTreePanel(QWidget):
    """List of tags with activity counts. Emits tag_selected(tag_name)."""

    tag_selected = Signal(str)  # tag name (or "__untagged__")

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._tag_task_map: dict[str, list[Task]] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.setStyleSheet(f"""
            QListWidget {{ border: none; background: transparent; font-size: 11px; }}
            QListWidget::item {{ padding: 5px 10px; border-radius: 4px; color: {t.text_primary}; }}
            QListWidget::item:selected {{ background: {t.accent}18; border-left: 3px solid {t.accent}; }}
            QListWidget::item:hover {{ background: {t.accent}08; }}
        """)
        layout.addWidget(self._list, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, date_from: date | None, date_to: date | None,
                partition_id: str | None, tag_filter: str | None = None) -> None:
        """Reload tag list with activity counts for the period."""
        from ...models.task_filter import TaskFilter

        f = TaskFilter(partition_id=partition_id)
        tasks = self._repository.search(f)

        # Group tasks by tag, count activities in period
        tag_data: dict[str, tuple[int, list[Task]]] = {}
        for task in tasks:
            entries = self._filter_entries(task, date_from, date_to)
            tag = (task.tags or ["__untagged__"])[0]
            if tag_filter and tag != tag_filter:
                continue
            if tag not in tag_data:
                tag_data[tag] = (0, [])
            count, task_list = tag_data[tag]
            tag_data[tag] = (count + len(entries), task_list + [task])

        # Sort by activity count desc
        sorted_tags = sorted(tag_data.items(), key=lambda x: x[1][0], reverse=True)

        self._list.blockSignals(True)
        self._list.clear()
        self._tag_task_map.clear()

        for tag, (count, task_list) in sorted_tags:
            display = tag if tag != "__untagged__" else "未分类"
            item = QListWidgetItem(f"{display}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self._list.addItem(item)
            self._tag_task_map[tag] = task_list

        self._list.blockSignals(False)

        # Auto-select first
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self.tag_selected.emit("")

    def get_tasks_for_tag(self, tag: str) -> list[Task]:
        return self._tag_task_map.get(tag, [])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_entries(self, task: Task, date_from: date | None, date_to: date | None) -> list[dict]:
        if date_from is None or date_to is None:
            return self._parse_log(task)
        entries = self._parse_log(task)
        return [e for e in entries if date_from <= self._entry_date(e) <= date_to]

    def _parse_log(self, task: Task) -> list[dict]:
        try:
            raw = task.activity_log
            if not raw or raw == "[]":
                return []
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []

    def _entry_date(self, entry: dict) -> date:
        try:
            ts = entry.get("ts", entry.get("time", ""))
            if "T" in ts:
                return datetime.fromisoformat(ts).date()
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").date()
        except (ValueError, TypeError):
            return date.today()

    def _on_item_changed(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        if current is None:
            return
        tag = current.data(Qt.ItemDataRole.UserRole)
        if tag:
            self.tag_selected.emit(tag)
