"""Tag list panel — checkable tag selector with select-all for activity analysis."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...utils.design_tokens import get_tokens


class TaskTreePanel(QWidget):
    """List of checkable tags with activity counts. Emits tag_selected(tag_name)."""

    tag_selected = Signal(str)
    checked_tags_changed = Signal()

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._tag_task_map: dict[str, list[Task]] = {}
        self._checked_tags: set[str] = set()
        self._active_tag: str | None = None
        self._all_checked = True
        self._build_ui()

    def _build_ui(self) -> None:
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Select-all toggle — match BatchToolbar style
        self._toggle_btn = QPushButton("取消全选")
        self._toggle_btn.setMinimumWidth(64)
        self._toggle_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 2px 6px; }")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self.toggle_all_checked)
        layout.addWidget(self._toggle_btn)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.itemChanged.connect(self._on_check_changed)
        self._list.setStyleSheet(f"""
            QListWidget {{ border: none; background: transparent; font-size: 11px; }}
            QListWidget::item {{ padding: 5px 10px; border-radius: 4px; color: {t.text_primary}; }}
            QListWidget::item:selected {{ background: {t.accent}18; border-left: 3px solid {t.accent}; }}
            QListWidget::item:hover {{ background: {t.accent}08; }}
            QListWidget::indicator {{
                width: 14px; height: 14px;
                border: 1.5px solid {t.border_primary};
                border-radius: 3px; background: transparent;
            }}
            QListWidget::indicator:checked {{
                background: {t.accent}; border-color: {t.accent};
            }}
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

        sorted_tags = sorted(tag_data.items(), key=lambda x: x[1][0], reverse=True)

        self._list.blockSignals(True)
        self._list.clear()
        self._tag_task_map.clear()
        self._checked_tags.clear()

        for tag, (count, task_list) in sorted_tags:
            display = tag if tag != "__untagged__" else "未分类"
            item = QListWidgetItem(f"{display}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._checked_tags.add(tag)
            self._list.addItem(item)
            self._tag_task_map[tag] = task_list

        self._all_checked = True
        self._toggle_btn.setText("取消全选")
        self._list.blockSignals(False)

        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._active_tag = None
            self.tag_selected.emit("")

    def get_tasks_for_tag(self, tag: str) -> list[Task]:
        return self._tag_task_map.get(tag, [])

    def get_checked_tags(self) -> list[str]:
        """Return checked tag names in list order."""
        ordered = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                tag = item.data(Qt.ItemDataRole.UserRole)
                if tag:
                    ordered.append(tag)
        return ordered

    def get_next_checked_tag(self, current_tag: str) -> str | None:
        """Return the next checked tag after current_tag, or None."""
        checked = self.get_checked_tags()
        try:
            idx = checked.index(current_tag)
            if idx + 1 < len(checked):
                return checked[idx + 1]
        except ValueError:
            pass
        return None

    def select_tag(self, tag: str) -> None:
        """Programmatically select and scroll to the given tag."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == tag:
                self._list.setCurrentItem(item)
                self._list.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)
                return

    def toggle_all_checked(self) -> None:
        """Toggle all tags between checked and unchecked."""
        self._list.blockSignals(True)
        new_state = Qt.CheckState.Unchecked if self._all_checked else Qt.CheckState.Checked
        self._checked_tags.clear()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                item.setCheckState(new_state)
                if new_state == Qt.CheckState.Checked:
                    tag = item.data(Qt.ItemDataRole.UserRole)
                    if tag:
                        self._checked_tags.add(tag)
        self._all_checked = not self._all_checked
        self._toggle_btn.setText("取消全选" if self._all_checked else "全选")
        self._list.blockSignals(False)
        self.checked_tags_changed.emit()

    def get_active_tag(self) -> str | None:
        return self._active_tag

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
        if tag and tag != self._active_tag:
            self._active_tag = tag
            self.tag_selected.emit(tag)

    def _on_check_changed(self, item: QListWidgetItem) -> None:
        tag = item.data(Qt.ItemDataRole.UserRole)
        if not tag:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_tags.add(tag)
        else:
            self._checked_tags.discard(tag)
        self._all_checked = all(
            self._list.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self._list.count())
        )
        self._toggle_btn.setText("取消全选" if self._all_checked else "全选")
        self.checked_tags_changed.emit()
