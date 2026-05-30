"""Progress overview list — tag-grouped task progress cards for the dashboard."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...utils.design_tokens import get_tokens


class _TagHeader(QWidget):
    """Collapsible tag group header."""

    clicked = Signal()

    def __init__(self, tag: str, task_count: int, activity_count: int,
                 expanded: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = expanded
        t = get_tokens()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 8, 4)
        layout.setSpacing(6)

        self._arrow = QLabel("▼" if expanded else "▶")
        self._arrow.setFixedWidth(14)
        self._arrow.setStyleSheet(f"color: {t.text_secondary}; font-size: 9px;")
        layout.addWidget(self._arrow)

        tag_label = QLabel(tag if tag != "__untagged__" else "未分类")
        tag_label.setStyleSheet(
            f"color: {t.accent}; font-size: 12px; font-weight: bold; "
            f"background: {t.accent}15; border-radius: 3px; padding: 1px 6px;"
        )
        layout.addWidget(tag_label)

        info = QLabel(f"{task_count}个任务, {activity_count}条活动")
        info.setStyleSheet(f"color: {t.text_secondary}; font-size: 9px;")
        layout.addWidget(info)

        layout.addStretch()

    def mousePressEvent(self, event) -> None:
        self._expanded = not self._expanded
        self._arrow.setText("▼" if self._expanded else "▶")
        self.clicked.emit()

    @property
    def expanded(self) -> bool:
        return self._expanded


class _TaskCard(QWidget):
    """Single task progress card."""

    report_requested = Signal(str)  # task_id

    def __init__(self, task: Task, activity_count: int, latest_activity: str,
                 start_progress: int, end_progress: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task_id = task.id
        t = get_tokens()

        self.setFixedHeight(52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Status dot
        status_colors = {
            "TODO": t.text_secondary,
            "DOING": "#f39c12",
            "DONE": t.success,
            "OVERDUE": t.danger,
        }
        dot_color = status_colors.get(task.status.value if hasattr(task.status, 'value') else str(task.status), t.text_secondary)
        dot = QLabel("●")
        dot.setFixedWidth(14)
        dot.setStyleSheet(f"color: {dot_color}; font-size: 10px;")
        layout.addWidget(dot)

        # Content area
        content = QVBoxLayout()
        content.setSpacing(2)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel(task.title)
        title.setStyleSheet(f"color: {t.text_primary}; font-size: 11px; font-weight: bold;")
        title_row.addWidget(title)

        # Tag badge
        tags = task.tags
        if tags:
            tag_str = tags[0] if isinstance(tags, list) else str(tags)
            tag_badge = QLabel(f"#{tag_str}" if not tag_str.startswith("#") else tag_str)
            tag_badge.setStyleSheet(
                f"color: {t.accent}; font-size: 9px; background: {t.accent}15; "
                f"border-radius: 3px; padding: 1px 5px;"
            )
            title_row.addWidget(tag_badge)

        title_row.addStretch()

        # Activity badge
        badge = QLabel(f"+{activity_count}条")
        badge.setStyleSheet(
            f"color: {t.accent}; font-size: 9px; font-weight: bold; "
            f"background: {t.accent}20; border-radius: 3px; padding: 1px 5px;"
        )
        title_row.addWidget(badge)

        content.addLayout(title_row)

        # Progress bar
        progress_widget = QWidget()
        progress_widget.setFixedHeight(6)
        progress_widget.setStyleSheet(
            f"background: {t.bg_secondary}; border-radius: 3px;"
        )
        if end_progress > 0 or start_progress > 0:
            pct = end_progress / 100.0
            bar = QLabel()
            bar.setFixedHeight(6)
            bar.setFixedWidth(int((self.width() - 80) * pct))
            bar.setStyleSheet(f"background: {t.accent}; border-radius: 3px;")
        content.addWidget(progress_widget)

        # Activity row
        act_row = QHBoxLayout()
        act_row.setSpacing(4)
        progress_text = QLabel(f"{start_progress}%→{end_progress}%")
        progress_text.setStyleSheet(f"color: {t.text_secondary}; font-size: 9px;")
        act_row.addWidget(progress_text)

        if latest_activity:
            snippet = QLabel(latest_activity[:50] + ("..." if len(latest_activity) > 50 else ""))
            snippet.setStyleSheet(f"color: {t.text_secondary}; font-size: 9px;")
            act_row.addWidget(snippet)

        act_row.addStretch()
        content.addLayout(act_row)

        layout.addLayout(content, 1)

        # Arrow (visible on hover)
        self._arrow = QLabel("→")
        self._arrow.setFixedWidth(20)
        self._arrow.setStyleSheet(f"color: {t.accent}; font-size: 12px; font-weight: bold;")
        self._arrow.setVisible(False)
        layout.addWidget(self._arrow)

    def enterEvent(self, event) -> None:
        t = get_tokens()
        self.setStyleSheet(
            f"background: {t.accent}10; border: 1px solid {t.border_primary}; "
            f"border-radius: 8px;"
        )
        self._arrow.setVisible(True)

    def leaveEvent(self, event) -> None:
        t = get_tokens()
        self.setStyleSheet(
            f"background: {t.accent}05; border: 1px solid transparent; "
            f"border-radius: 8px;"
        )
        self._arrow.setVisible(False)

    def mousePressEvent(self, event) -> None:
        self.report_requested.emit(self._task_id)


class ProgressOverviewList(QWidget):
    """Scrollable tag-grouped list of task progress cards.

    Shows tasks with activity in the selected period, grouped by tag,
    sorted by activity count descending.
    """

    report_requested = Signal(str, object, object, str)  # task_id, date_from, date_to, label

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._current_date_from: date | None = None
        self._current_date_to: date | None = None
        self._current_label: str = ""
        self._tag_groups: dict[str, list] = {}
        self._expanded_tags: dict[str, bool] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        t = get_tokens()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        main_layout.addWidget(self._scroll)

        # Initial empty state
        self._show_empty_hint("选择时段查看任务进度")

    def _show_empty_hint(self, text: str) -> None:
        self._clear_content()
        t = get_tokens()
        hint = QLabel(text)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"color: {t.text_secondary}; font-size: 12px; padding: 32px;"
        )
        self._content_layout.insertWidget(0, hint)

    def _clear_content(self) -> None:
        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self, date_from: date | None, date_to: date | None,
                partition_id: str | None, tag_filter: str | None = None) -> None:
        """Refresh the progress overview for a given period."""
        self._current_date_from = date_from
        self._current_date_to = date_to
        self._clear_content()

        if date_from is None or date_to is None:
            # Show all tasks (no period filter)
            self._show_all_tasks(partition_id, tag_filter)
        else:
            self._show_period_tasks(date_from, date_to, partition_id, tag_filter)

        # Add stretch at end
        self._content_layout.addStretch()

    def _show_all_tasks(self, partition_id: str | None, tag_filter: str | None) -> None:
        """Show all tasks in partition, sorted by recent activity."""
        from ...models.task_filter import TaskFilter
        f = TaskFilter(partition_id=partition_id)
        tasks = self._repository.search(f)
        if not tasks:
            self._show_empty_hint("当前分区暂无任务")
            return

        # Group by tag, sort by most recent activity
        groups: dict[str, list[tuple]] = {}
        for task in tasks:
            entries = self._parse_activity_log(task)
            activity_count = len(entries)
            latest = entries[-1]["content"] if entries else ""
            tag = task.tags[0] if task.tags else "__untagged__"
            if tag_filter and tag != tag_filter:
                continue
            groups.setdefault(tag, []).append((
                task, activity_count, latest,
                entries[0]["progress"] if entries else task.progress,
                entries[-1]["progress"] if entries else task.progress,
            ))

        self._build_tag_groups(groups)

    def _show_period_tasks(self, date_from: date, date_to: date,
                           partition_id: str | None, tag_filter: str | None) -> None:
        """Show tasks with activity in the period."""
        from ...models.task_filter import TaskFilter
        f = TaskFilter(partition_id=partition_id)
        tasks = self._repository.search(f)

        groups: dict[str, list[tuple]] = {}
        for task in tasks:
            entries = self._parse_activity_log(task)
            period_entries = [
                e for e in entries
                if date_from <= self._entry_date(e) <= date_to
            ]
            if not period_entries:
                continue
            activity_count = len(period_entries)
            latest = period_entries[-1]["content"] if period_entries else ""
            start_progress = period_entries[0].get("progress", task.progress)
            end_progress = period_entries[-1].get("progress", task.progress)
            tag = task.tags[0] if task.tags else "__untagged__"
            if tag_filter and tag != tag_filter:
                continue
            groups.setdefault(tag, []).append((
                task, activity_count, latest, start_progress, end_progress,
            ))

        if not groups:
            self._show_empty_hint("此时段内暂无活动记录\n尝试选择其他时段或自定义范围")
            return

        self._build_tag_groups(groups)

    def _build_tag_groups(self, groups: dict[str, list[tuple]]) -> None:
        """Build tag group headers + task cards from grouped data."""
        # Sort tags by total activity count descending
        sorted_tags = sorted(groups.items(), key=lambda x: sum(item[1] for item in x[1]), reverse=True)

        for tag, items in sorted_tags:
            # Sort items by activity count descending
            items.sort(key=lambda x: x[1], reverse=True)
            total_activity = sum(item[1] for item in items)

            # Tag header
            expanded = self._expanded_tags.get(tag, True)
            header = _TagHeader(tag, len(items), total_activity, expanded)
            header.clicked.connect(lambda t=tag, h=header: self._on_tag_toggle(t, h, items))
            self._content_layout.addWidget(header)

            # Task cards (visible if expanded)
            for task, act_count, latest, start_p, end_p in items:
                card = _TaskCard(task, act_count, latest, start_p, end_p)
                card.report_requested.connect(self._on_report_requested)
                card.setVisible(expanded)
                card.setObjectName(f"card_{tag}")
                self._content_layout.addWidget(card)

    def _on_tag_toggle(self, tag: str, header: _TagHeader, items: list) -> None:
        self._expanded_tags[tag] = header.expanded
        # Toggle visibility of all cards under this tag
        for i in range(self._content_layout.count()):
            w = self._content_layout.itemAt(i).widget()
            if w and w.objectName() == f"card_{tag}":
                w.setVisible(header.expanded)

    def _on_report_requested(self, task_id: str) -> None:
        self.report_requested.emit(
            task_id,
            self._current_date_from,
            self._current_date_to,
            self._current_label,
        )

    def _parse_activity_log(self, task: Task) -> list[dict]:
        """Parse activity_log JSON safely."""
        try:
            raw = task.activity_log
            if not raw or raw == "[]":
                return []
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []

    def _entry_date(self, entry: dict) -> date:
        """Extract date from an activity log entry."""
        try:
            ts = entry.get("time", "")
            if "T" in ts:
                return datetime.fromisoformat(ts).date()
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").date()
        except (ValueError, TypeError):
            return date.today()
