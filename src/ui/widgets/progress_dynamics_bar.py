"""Progress Dynamics Bar — period toggles with activity-based ranking."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
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
    """进度动态栏: 5 period toggles that rank tasks by activity within the period.

    Signals:
        progress_filter_activated(TaskFilter): emitted when a period is clicked
    """

    progress_filter_activated = Signal(TaskFilter)

    def __init__(
        self,
        repository: TaskRepository,
        enabled_periods: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._enabled_periods = enabled_periods or [p[0] for p in PERIODS]
        self._active_period = ""  # unclicked by default
        self._synced_key: str | None = None
        self._partition_id: str | None = None
        self._build_ui()

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
        self._hint_label = QLabel()
        self._hint_label.setStyleSheet(
            f"font-size: 10px; color: {get_tokens().text_secondary};"
        )
        layout.addWidget(self._hint_label)
        layout.addStretch()

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
        if period_key is None:
            self._active_period = ""
        self._hint_label.setText("")

    def reset_to_unclicked(self) -> None:
        """Restore synced period to unclicked state (after task changes)."""
        if self._synced_key:
            for key, btn in self._period_buttons.items():
                btn.setEnabled(key == self._synced_key)
                btn.setChecked(False)
            self._active_period = ""
            self._hint_label.setText("")

    def refresh(self) -> None:
        """Re-query and update the hint label with the most active task."""
        period_start, period_end = _get_period_range(self._active_period)
        filter_ = TaskFilter(
            partition_id=self._partition_id,
            date_from=period_start,
            date_to=period_end,
            sort_by=[SortCriterion("progress", ascending=False)],
        )
        tasks = self._repository.search(filter_)
        if tasks:
            ranked = self._rank_tasks(tasks, period_start, period_end)
            best = ranked[0] if ranked else None
            if best:
                count = sum(
                    1 for e in best.activity_log
                    if self._ts_in_range(e.get("ts", ""), period_start, period_end)
                )
                self._hint_label.setText(f"最活跃: {best.title} (+{count}条)")
                return
        self._hint_label.setText("")

    def build_filter(self) -> TaskFilter:
        """Build TaskFilter for the active period, sorted by activity descending."""
        period_start, period_end = _get_period_range(self._active_period)
        return TaskFilter(
            partition_id=self._partition_id,
            date_from=period_start,
            date_to=period_end,
            sort_by=[SortCriterion("progress", ascending=False)],
        )

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
        # Toggle: if already clicked, unclick and restore 速览-based sort
        if self._active_period == period_key:
            self._active_period = ""
            for key, btn in self._period_buttons.items():
                btn.setChecked(False)
            self._hint_label.setText("")
            # Emit with urgency sort so main_window restores 速览 ordering
            self.progress_filter_activated.emit(TaskFilter(
                partition_id=self._partition_id,
                sort_by=[SortCriterion("urgency", ascending=True)],
            ))
            return
        self._active_period = period_key
        for key, btn in self._period_buttons.items():
            btn.setChecked(key == period_key)
        self.refresh()
        self.progress_filter_activated.emit(self.build_filter())
