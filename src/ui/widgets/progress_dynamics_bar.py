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
from ...models.task_filter import SortCriterion, TaskFilter
from ...models.task_status import TaskStatus

PERIODS = [
    ("yesterday", "昨天"),
    ("today", "今天"),
    ("last_week", "上周"),
    ("week", "本周"),
    ("last_month", "上月"),
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
    elif period_key == "last_week":
        last_monday = today - timedelta(days=today.isoweekday() + 6)
        last_sunday = last_monday + timedelta(days=6)
        return last_monday, last_sunday
    elif period_key == "week":
        days_since_monday = today.isoweekday() - 1
        monday = today - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        return monday, sunday
    elif period_key == "last_month":
        first_of_this_month = today.replace(day=1)
        last_day_of_last_month = first_of_this_month - timedelta(days=1)
        first_of_last_month = last_day_of_last_month.replace(day=1)
        return first_of_last_month, last_day_of_last_month
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
        layout.setSpacing(3)

        self._period_buttons: dict[str, QPushButton] = {}
        for key, label in PERIODS:
            btn = QPushButton(label)
            btn.setObjectName("periodBtn")
            btn.setMinimumWidth(48)
            btn.setCheckable(True)
            btn.setEnabled(key in self._enabled_periods)
            btn.setChecked(key == self._active_period)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._on_period_clicked(k))
            if not btn.isEnabled():
                btn.setToolTip("此周期已在设置中禁用")
            self._period_buttons[key] = btn
            layout.addWidget(btn)

        layout.addSpacing(12)
        self._carousel_label = QLabel()
        self._carousel_label.setObjectName("carouselLabel")
        self._carousel_label.setWordWrap(False)
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

    def reset_to_unclicked(self) -> None:
        """Restore to unclicked hint mode — all period buttons remain enabled."""
        self._active_period = ""
        for btn in self._period_buttons.values():
            btn.setEnabled(True)
            btn.setChecked(False)
        self._enter_hint_mode()
        self._carousel_label.setText("")

    def refresh(self) -> None:
        """Re-query repository and update display based on current mode."""
        if not self._active_period:
            return
        filter_ = TaskFilter(partition_id=self._partition_id)
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
                if self._ts_in_range(e.get("ts", e.get("time", "")), period_start, period_end)
            )
            suffix = self.deadline_suffix(task)
            self._items.append({
                "task_id": task.id,
                "text": task.title,
                "activity_count": count,
                "suffix": suffix,
            })
        self._scroll_index = 0
        if self._items:
            self._enter_carousel_mode()
            self._render()
        else:
            self._enter_hint_mode()

    def build_filter(self) -> TaskFilter:
        """Build TaskFilter for the active period, sorted by urgency."""
        return TaskFilter(
            partition_id=self._partition_id,
            sort_by=[SortCriterion("urgency", ascending=True)],
        )

    def filter_tasks_by_activity(self, tasks: list[Task]) -> list[Task]:
        """Return tasks that have activity_log entries in the active period."""
        if not self._active_period:
            return tasks
        period_start, period_end = _get_period_range(self._active_period)
        result = []
        for t in tasks:
            for e in t.activity_log:
                ts = e.get("ts", e.get("time", ""))
                if self._ts_in_range(ts, period_start, period_end):
                    result.append(t)
                    break
        return result

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
            suffix = self.deadline_suffix(best_task)
            self._carousel_label.setText(
                f"最新: {best_task.title} — {best_content}{suffix}"
            )
            self._carousel_label.setToolTip(
                f"{best_task.title}"
                f"{' — 截止: ' + best_task.deadline_date.isoformat() if best_task.deadline_date else ''}"
                f"{' ' + best_task.deadline_time if best_task.deadline_time else ''}"
            )
        else:
            self._carousel_label.setText("")
            self._carousel_label.setToolTip("")

    # ------------------------------------------------------------------
    # Carousel mode (clicked) -- ranked rotation
    # ------------------------------------------------------------------

    def _render(self) -> None:
        if self._items:
            item = self._items[self._scroll_index]
            suffix = item.get("suffix", "")
            self._carousel_label.setText(
                f"+{item['activity_count']}条 {item['text']}{suffix}"
            )
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
        """Rank tasks by activity_count * deadline_weight DESC, then progress DESC.

        Tasks due today or overdue get a 2× boost so they surface prominently.
        """
        today = date.today()

        def _deadline_boost(task: Task) -> float:
            """1.0 for normal, 2.0 for today/overdue, 1.5 for within 3 days."""
            dl = task.deadline_date or task.scheduled_date
            if dl is None:
                return 1.0
            days = (today - dl).days
            if days >= 0:
                return 2.0  # overdue or today
            elif days >= -3:
                return 1.5  # within 3 days
            return 1.0

        def score(task: Task) -> tuple[float, int]:
            count = sum(
                1 for e in task.activity_log
                if self._ts_in_range(e.get("ts", e.get("time", "")), period_start, period_end)
            )
            return (count * _deadline_boost(task), task.progress)

        return sorted(tasks, key=score, reverse=True)

    @staticmethod
    def _ts_in_range(ts: str, start: date, end: date) -> bool:
        """与 TaskTreePanel._entry_date 行为一致的 timestamp 解析。"""
        if not ts:
            return False
        try:
            if "T" in ts:
                dt = datetime.fromisoformat(ts)
            else:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return start <= dt.date() <= end
        except (ValueError, TypeError):
            return False

    @staticmethod
    def deadline_suffix(task: Task) -> str:
        """Return a compact deadline indicator for carousel display.

        Examples: ``⏰14:30``, ``⏰2h后``, ``⚠逾期3天``, ``📅6/15``.
        """
        if task.status == TaskStatus.DONE:
            return ""
        dl = task.deadline_date or task.scheduled_date
        if dl is None:
            return ""
        today = date.today()
        days = (today - dl).days
        if days > 0:
            return f"  ⚠逾期{days}天"
        elif days == 0:
            if task.deadline_time:
                try:
                    h, m = map(int, task.deadline_time.split(":")[:2])
                    now = datetime.now()
                    dl_dt = datetime(dl.year, dl.month, dl.day, h, m)
                    remaining = (dl_dt - now).total_seconds()
                    if remaining < 0:
                        return "  ⚠已超时"
                    elif remaining < 3600:
                        return f"  ⏰{int(remaining // 60)}m后"
                    elif remaining < 3600 * 6:
                        return f"  ⏰{int(remaining // 3600)}h后"
                    else:
                        return f"  ⏰{h:02d}:{m:02d}"
                except (ValueError, IndexError):
                    pass
            return "  ⏰今天"
        elif days < 0:
            return f"  📅{dl.month}/{dl.day}"
        return ""

    # ------------------------------------------------------------------
    # Period toggle
    # ------------------------------------------------------------------

    def _on_period_clicked(self, period_key: str) -> None:
        if self._active_period == period_key:
            # Toggle off: back to unclicked hint mode, restore default sort
            self.reset_to_unclicked()
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
