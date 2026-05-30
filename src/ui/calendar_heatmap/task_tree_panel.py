"""Task tree panel — tag-grouped task tree for activity analysis."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...utils.design_tokens import get_tokens

_STATUS_COLORS = {
    "TODO": "#5b8def",
    "DOING": "#f39c12",
    "DONE": "#2ecc71",
    "OVERDUE": "#e74c3c",
}


class TaskTreePanel(QWidget):
    """Tag-grouped task tree with search filter. Emits task_selected(task_id)."""

    task_selected = Signal(str)

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._tasks: list[Task] = []
        self._task_map: dict[str, Task] = {}
        self._current_date_from: date | None = None
        self._current_date_to: date | None = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._apply_filter)
        self._build_ui()

    def _build_ui(self) -> None:
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Search row
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 搜索任务...")
        self._search_input.setFixedHeight(26)
        self._search_input.textChanged.connect(lambda: self._search_timer.start())
        search_row.addWidget(self._search_input)
        layout.addLayout(search_row)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tree.currentItemChanged.connect(self._on_item_changed)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                border: none; background: transparent;
                font-size: 11px; color: {t.text_primary};
            }}
            QTreeWidget::item {{
                padding: 3px 4px; border-radius: 4px;
            }}
            QTreeWidget::item:selected {{
                background: {t.accent}18; color: {t.text_primary};
            }}
            QTreeWidget::item:hover {{
                background: {t.accent}08;
            }}
        """)
        layout.addWidget(self._tree, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, date_from: date | None, date_to: date | None,
                partition_id: str | None, tag_filter: str | None = None) -> None:
        """Reload tree with tasks filtered by period and partition."""
        self._current_date_from = date_from
        self._current_date_to = date_to

        from ...models.task_filter import TaskFilter
        f = TaskFilter(partition_id=partition_id)
        tasks = self._repository.search(f)
        self._tasks = tasks
        self._task_map = {t.id: t for t in tasks}

        # Build activity data per task
        task_activity: dict[str, dict] = {}
        for task in tasks:
            entries = self._filter_entries(task, date_from, date_to)
            tag = (task.tags or ["__untagged__"])[0]
            if tag_filter and tag != tag_filter:
                continue
            task_activity[task.id] = {
                "task": task,
                "count": len(entries),
                "tag": tag,
                "entries": entries,
            }

        self._build_tree(task_activity)

    def _filter_entries(self, task: Task, date_from: date | None, date_to: date | None) -> list[dict]:
        """Filter activity_log entries within date range."""
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

    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------

    def _build_tree(self, task_activity: dict[str, dict]) -> None:
        t = get_tokens()
        search_text = self._search_input.text().lower().strip()
        self._tree.blockSignals(True)
        self._tree.clear()

        # Group by tag
        groups: dict[str, list[dict]] = {}
        for data in task_activity.values():
            tag = data["tag"]
            if search_text and search_text not in data["task"].title.lower():
                continue
            groups.setdefault(tag, []).append(data)

        # Sort tags by total activity
        sorted_tags = sorted(groups.items(),
                             key=lambda x: sum(d["count"] for d in x[1]), reverse=True)

        first_task_item = None
        for tag, items in sorted_tags:
            total_count = sum(d["count"] for d in items)
            # Sort items by activity count desc
            items.sort(key=lambda d: d["count"], reverse=True)

            # Tag header
            tag_display = tag if tag != "__untagged__" else "未分类"
            tag_item = QTreeWidgetItem()
            tag_item.setText(0, f"▼ {tag_display}  {len(items)}任务 {total_count}活动")
            tag_item.setData(0, Qt.ItemDataRole.UserRole, f"__tag__{tag}")
            tag_item.setForeground(0, Qt.GlobalColor.gray)  # placeholder, overridden by style
            tag_item.setFlags(tag_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = tag_item.font(0)
            font.setBold(True)
            font.setPointSize(10)
            tag_item.setFont(0, font)

            for data in items:
                task = data["task"]
                count = data["count"]

                status = task.status.value if hasattr(task.status, 'value') else str(task.status)
                dot = "●" if count > 0 else "○"
                status_color = _STATUS_COLORS.get(status, "#888")
                if count == 0:
                    status_color = "#aaa"

                child = QTreeWidgetItem()
                child.setText(0, f"{dot} {task.title}   +{count}条")
                child.setData(0, Qt.ItemDataRole.UserRole, task.id)
                child.setForeground(0, Qt.GlobalColor.gray)  # placeholder
                tag_item.addChild(child)

                if first_task_item is None:
                    first_task_item = child

            self._tree.addTopLevelItem(tag_item)
            tag_item.setExpanded(True)

        self._tree.blockSignals(False)

        # Auto-select first task
        if first_task_item:
            self._tree.setCurrentItem(first_task_item)
        else:
            self.task_selected.emit("")

    def _apply_filter(self) -> None:
        """Reapply tree filtering based on search text."""
        from ...models.task_filter import TaskFilter
        f = TaskFilter(partition_id=None)
        tasks = self._repository.search(f)
        task_activity = {}
        for task in tasks:
            entries = self._filter_entries(task, self._current_date_from, self._current_date_to)
            tag = (task.tags or ["__untagged__"])[0]
            task_activity[task.id] = {
                "task": task, "count": len(entries),
                "tag": tag, "entries": entries,
            }
        self._build_tree(task_activity)

    def _on_item_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        if current is None:
            return
        task_id = current.data(0, Qt.ItemDataRole.UserRole)
        if task_id and not str(task_id).startswith("__tag__"):
            self.task_selected.emit(str(task_id))
