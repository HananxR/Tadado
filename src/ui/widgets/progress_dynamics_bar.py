"""Progress Dynamics Bar -- period toggles with activity-based ranking."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_filter import TaskFilter, SortCriterion
from ...utils.design_tokens import get_tokens

PERIODS = [
    ("yesterday", "昨天"),
    ("today", "今天"),
    ("week", "本周"),
    ("month", "本月"),
]


def _get_period_range(period_key: str) -> tuple[date, date]:
    """Return (start_date, end_date) inclusive for a period key."""
    today = date.today()
    if period_key == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    elif period_key == "today":
        return today, today
    elif period_key == "week":
        days_since_monday = today.isoweekday() - 1
        monday = today - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        return monday, sunday
    elif period_key == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return start, end
    elif period_key == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    else:
        return today, today


class ProgressDynamicsBar(QWidget):
    """进度动态栏: period toggles that rank tasks by activity within the period.

    Dual-mode display (always 1 column):
      - Unclicked: shows latest activity of the most recently active task
      - Clicked:   carousel of top active tasks, rotating every interval_seconds

    Signals:
        progress_filter_activated(TaskFilter): emitted when a period is clicked/toggled
        task_clicked(str): emitted when the carousel label is clicked (task_id)
    """

    progress_filter_activated = Signal(TaskFilter)
    task_clicked = Signal(str)

    def __init__(
        self,
        repository: TaskRepository,
        enabled_periods: list[str] | None = None,
        max_items: int = 6,
        interval_seconds: int = 5,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._enabled_periods = enabled_periods or [p[0] for p in PERIODS]
        self._active_period = ""  # unclicked by default
        self._synced_key: str | None = None
        self._partition_id: str | None = None
        self._max_items = max_items
        self._interval_ms = interval_seconds * 1000
        self._items: list[dict] = []
        self._scroll_index = 0
        self._carousel_active = False

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        # Timer starts stopped; only runs in carousel mode

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self._period_buttons: dict[str, QPushButton] = {}
        for key, label in PERIODS:
            btn = QPushButton(label)
            btn.setMinimumWidth(52)
            btn.setCheckable(True)
            btn.setEnabled(key in self._enabled_periods)
            btn.setChecked(key == self._active_period)
            t = get_tokens()
            btn.setStyleSheet(
                f"QPushButton {{ font-size: 10px; padding: 2px 6px; color: {t.text_primary}; background: transparent; border: 1px solid {t.border_primary}; }}"
                f"QPushButton:checked {{ background: {t.accent}; color: {t.text_on_accent}; font-weight: bold; border: none; }}"
                f"QPushButton:disabled {{ color: rgba(128,128,128,0.35); background: transparent; border: 1px solid transparent; }}"
            )
            btn.clicked.connect(lambda checked=False, k=key: self._on_period_clicked(k))
            if not btn.isEnabled():
                btn.setToolTip("此周期已在设置中禁用")
            self._period_buttons[key] = btn
            layout.addWidget(btn)

        layout.addSpacing(12)
        self._carousel_label = QLabel()
        self._carousel_label.setWordWrap(False)
        self._carousel_label.setStyleSheet(
            "QLabel { padding: 2px 8px; border-radius: 4px; "
            "font-size: 10px; background: rgba(128,128,128,0.08); "
            f"color: {get_tokens().text_secondary}; " + "}"
        )
        layout.addWidget(self._carousel_label, 1)
        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_partition_id(self, pid: str | None) -> None:
        self._partition_id = pid

    def set_enabled_periods(self, periods: list[str]) -> None:
        self._enabled_periods = list(periods)
        for key, btn in self._period_buttons.items():
            btn.setEnabled(key in self._enabled_periods)

    def set_synced_period(self, period_key: str | None) -> None:
        """Sync with 速览栏: only matching period clickable, others disabled."""
        self._synced_key = period_key
        for key, btn in self._period_buttons.items():
            if period_key is None:
                btn.setEnabled(False)
            else:
                btn.setEnabled(key == period_key)
            btn.setChecked(False)
        self._active_period = ""
        self._enter_hint_mode()

    def reset_to_unclicked(self) -> None:
        """Restore synced period to unclicked state (after task changes)."""
        if self._synced_key:
            for key, btn in self._period_buttons.items():
                btn.setEnabled(key == self._synced_key)
                btn.setChecked(False)
            self._active_period = ""
            self._enter_hint_mode()

    def refresh(self) -> None:
        """Re-query repository and update display based on current mode."""
        period_start, period_end = _get_period_range(self._active_period)
        filter_ = TaskFilter(
            partition_id=self._partition_id,
            date_from=period_start,
            date_to=period_end,
            sort_by=[SortCriterion("progress", ascending=False)],
        )
        tasks = self._repository.search(filter_)
        self.set_items(tasks)

    def set_items(self, tasks: list[Task]) -> None:
        """Populate display from a pre-fetched task list.

        In unclicked (hint) mode: shows the most recent activity log entry.
        In clicked (carousel) mode: ranks by activity count and starts rotation.
        """
        if not self._active_period:
            self._show_latest_activity(tasks)
            return
        # Carousel mode
        period_start, period_end = _get_period_range(self._active_period)
        ranked = self._rank_tasks(tasks, period_start, period_end)
        self._items = []
        for task in ranked[:self._max_items]:
            count = sum(
                1 for e in task.activity_log
                if self._ts_in_range(e.get("ts", ""), period_start, period_end)
            )
            self._items.append({
                "task_id": task.id,
                "text": task.title,
                "activity_count": count,
            })
        self._scroll_index = 0
        if self._items:
            self._enter_carousel_mode()
            self._render()
        else:
            self._enter_hint_mode()

    def build_filter(self) -> TaskFilter:
        """Build TaskFilter for the active period, sorted by activity count descending."""
        period_start, period_end = _get_period_range(self._active_period)
        activity_field = f"activity_{self._active_period}" if self._active_period else "activity_today"
        return TaskFilter(
            partition_id=self._partition_id,
            date_from=period_start,
            date_to=period_end,
            sort_by=[SortCriterion(activity_field, ascending=False)],
        )

    # ------------------------------------------------------------------
    # Hint mode (unclicked) -- latest activity
    # ------------------------------------------------------------------

    def _show_latest_activity(self, tasks: list[Task]) -> None:
        """Find and display the most recent activity_log entry across all tasks."""
        best_ts: str | None = None
        best_task: Task | None = None
        best_content: str = ""
        for task in tasks:
            for entry in task.activity_log:
                ts = entry.get("ts", "")
                if ts and (best_ts is None or ts > best_ts):
                    best_ts = ts
                    best_task = task
                    best_content = entry.get("content", "")
        if best_task:
            self._carousel_label.setText(f"最新: {best_task.title} — {best_content}")
            self._carousel_label.setToolTip(best_task.title)
        else:
            self._carousel_label.setText("")
            self._carousel_label.setToolTip("")

    # ------------------------------------------------------------------
    # Carousel mode (clicked) -- ranked rotation
    # ------------------------------------------------------------------

    def _render(self) -> None:
        if self._items:
            item = self._items[self._scroll_index]
            self._carousel_label.setText(f"+{item['activity_count']}条 {item['text']}")
            self._carousel_label.setToolTip(item["text"])

    def _scroll(self) -> None:
        if not self._items:
            return
        self._scroll_index = (self._scroll_index + 1) % len(self._items)
        self._render()

    def _make_click_handler(self):
        def handler(event) -> None:
            if self._items and self._scroll_index < len(self._items):
                self.task_clicked.emit(self._items[self._scroll_index]["task_id"])
        return handler

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _enter_hint_mode(self) -> None:
        """Switch to hint (unclicked) display: stop timer, clear items, non-interactive."""
        self._timer.stop()
        self._carousel_active = False
        self._items = []
        self._scroll_index = 0
        self._carousel_label.setCursor(Qt.CursorShape.ArrowCursor)
        self._carousel_label.mousePressEvent = lambda event: None

    def _enter_carousel_mode(self) -> None:
        """Switch to carousel (clicked) display: start timer, make label interactive."""
        self._carousel_active = True
        self._carousel_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._carousel_label.mousePressEvent = self._make_click_handler()
        self._timer.start(self._interval_ms)

    # ------------------------------------------------------------------
    # Rank computation
    # ------------------------------------------------------------------

    def _rank_tasks(self, tasks: list[Task], period_start: date, period_end: date) -> list[Task]:
        """Rank tasks by activity_count DESC, then progress DESC."""
        def score(task: Task) -> tuple[int, int]:
            count = sum(
                1 for e in task.activity_log
                if self._ts_in_range(e.get("ts", ""), period_start, period_end)
            )
            return (count, task.progress)
        return sorted(tasks, key=score, reverse=True)

    @staticmethod
    def _ts_in_range(ts: str, start: date, end: date) -> bool:
        try:
            dt = datetime.fromisoformat(ts)
            return start <= dt.date() <= end
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Period toggle
    # ------------------------------------------------------------------

    def _on_period_clicked(self, period_key: str) -> None:
        if self._active_period == period_key:
            # Toggle off: back to unclicked hint mode
            self._active_period = ""
            for key, btn in self._period_buttons.items():
                btn.setChecked(False)
            self._enter_hint_mode()
            self._carousel_label.setText("")
            self.progress_filter_activated.emit(TaskFilter(
                partition_id=self._partition_id,
                sort_by=[SortCriterion("urgency", ascending=True)],
            ))
            return
        # Toggle on: enter carousel mode
        self._active_period = period_key
        for key, btn in self._period_buttons.items():
            btn.setChecked(key == period_key)
        self.refresh()
        self.progress_filter_activated.emit(self.build_filter())
