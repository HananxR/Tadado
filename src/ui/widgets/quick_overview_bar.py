"""Quick Overview Bar — combined carousel + preset buttons with urgency scoring."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_filter import TaskFilter, SortCriterion
from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens

PRESETS = [
    ("yesterday", "昨天"),
    ("today", "今天"),
    ("last_week", "上周"),
    ("week", "本周"),
    ("last_month", "上月"),
    ("month", "本月"),
]


class QuickOverviewBar(QWidget):
    """速览栏: carousel + preset filter buttons with urgency-based sorting.

    Signals:
        preset_activated(str): emitted when user clicks a preset button
            — "all" | "today" | "week" | "overdue"
    """

    preset_activated = Signal(str)
    task_clicked = Signal(str)  # task_id

    def __init__(
        self,
        repository: TaskRepository,
        partition_id: str | None = None,
        max_items: int = 10,
        group_size: int = 3,
        interval_seconds: int = 5,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._partition_id = partition_id
        self._max_items = max_items
        self._group_size = group_size
        self._active_preset = "today"
        self._items: list[dict] = []
        self._scroll_index = 0

        self._build_ui()

        # Auto-scroll timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.start(interval_seconds * 1000)

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # Left: Preset buttons
        self._preset_buttons: dict[str, QPushButton] = {}
        for key, label in PRESETS:
            btn = QPushButton(label)
            btn.setMinimumWidth(48)
            btn.setCheckable(True)
            btn.setChecked(key == self._active_preset)
            t = get_tokens()
            btn.setStyleSheet(
                f"QPushButton {{ font-size: 10px; padding: 2px 5px; color: {t.text_secondary}; background: transparent; border: 1px solid {t.border_primary}; }}"
                f"QPushButton:checked {{ background: {t.accent}; color: {t.text_on_accent}; font-weight: bold; border: none; }}"
            )
            btn.clicked.connect(lambda checked=False, k=key: self.activate_preset(k))
            self._preset_buttons[key] = btn
            main_layout.addWidget(btn)

        # Right: Carousel (3 tasks per group)
        self._carousel_labels: list[QLabel] = []
        for i in range(self._group_size):
            label = QLabel()
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.setWordWrap(False)
            label.setStyleSheet(
                "QLabel { padding: 2px 8px; border-radius: 4px; "
                "font-size: 10px; background: rgba(128,128,128,0.08); }"
            )
            label.mousePressEvent = self._make_click_handler(i)
            self._carousel_labels.append(label)
            main_layout.addWidget(label, 1)
        main_layout.addStretch()

    def set_partition_id(self, pid: str | None) -> None:
        self._partition_id = pid

    def refresh(self) -> None:
        if not hasattr(self, '_repository') or self._repository is None:
            return
        filter_ = self.build_filter()
        tasks = self._repository.search(filter_)
        self.set_items(tasks)

    def set_items(self, tasks: list[Task]) -> None:
        """Populate carousel with tasks sorted by active preset urgency (ascending)."""
        scored = [(t, self._urgency_for_preset(t)) for t in tasks]
        scored.sort(key=lambda x: x[1])  # ascending (smaller = more urgent)

        self._items = []
        for task, score in scored[: self._max_items]:
            urgency_text = self._urgency_label(task, score)
            # Color: overdue=red, today=amber, future=green, none=grey
            t2 = get_tokens()
            if task.status == TaskStatus.DONE:
                lc = t2.success
            elif task.deadline_date or task.scheduled_date:
                dl = task.deadline_date or task.scheduled_date
                days = (date.today() - dl).days if dl else 0
                if days > 0:
                    lc = t2.danger
                elif days == 0:
                    lc = "#f39c12"  # amber — functional color, same in both themes
                else:
                    lc = t2.success
            else:
                lc = t2.text_secondary
            self._items.append({
                "task_id": task.id,
                "text": f"{task.title}",
                "color": task.status.display_color,
                "urgency": urgency_text,
                "label_color": lc,
            })

        self._scroll_index = 0
        self._render()

    def activate_preset(self, preset: str) -> None:
        self._active_preset = preset
        for key, btn in self._preset_buttons.items():
            btn.setChecked(key == preset)
        self._scroll_index = 0
        self.preset_activated.emit(preset)

    # ------------------------------------------------------------------
    # Urgency computation
    # ------------------------------------------------------------------

    def _urgency_for_preset(self, task: Task) -> float:
        if task.status == TaskStatus.DONE:
            return float("inf")
        dl_date = task.deadline_date or task.scheduled_date
        if dl_date is None:
            return float("inf") - 1

        dl_time_str = task.deadline_time or "23:59"
        try:
            h, m = map(int, dl_time_str.split(":")[:2])
        except (ValueError, IndexError):
            h, m = 23, 59
        deadline_dt = datetime(dl_date.year, dl_date.month, dl_date.day, h, m, 0)

        if self._active_preset == "yesterday":
            yesterday = date.today() - timedelta(days=1)
            yesterday_end = datetime.combine(yesterday, datetime.max.time())
            return (yesterday_end - deadline_dt).total_seconds()
        elif self._active_preset == "today":
            today_end = datetime.combine(date.today(), datetime.max.time())
            return (today_end - deadline_dt).total_seconds()
        elif self._active_preset == "last_week":
            today = date.today()
            last_sunday = today - timedelta(days=today.isoweekday())
            last_sunday_end = datetime.combine(last_sunday, datetime.max.time())
            return (last_sunday_end - deadline_dt).total_seconds()
        elif self._active_preset == "week":
            today = date.today()
            days_until_sunday = 7 - today.isoweekday()
            sunday = today + timedelta(days=days_until_sunday)
            sunday_end = datetime.combine(sunday, datetime.max.time())
            return (sunday_end - deadline_dt).total_seconds()
        elif self._active_preset == "last_month":
            today = date.today()
            first_of_this_month = today.replace(day=1)
            last_day_of_last_month = first_of_this_month - timedelta(days=1)
            last_month_end = datetime.combine(last_day_of_last_month, datetime.max.time())
            return (last_month_end - deadline_dt).total_seconds()
        elif self._active_preset == "month":
            import calendar as _cal
            today = date.today()
            _, last = _cal.monthrange(today.year, today.month)
            month_end = datetime.combine(today.replace(day=last), datetime.max.time())
            return (month_end - deadline_dt).total_seconds()
        else:
            return (datetime.now() - deadline_dt).total_seconds()

    @staticmethod
    def _urgency_label(task: Task, score: float) -> str:
        if task.status == TaskStatus.DONE:
            return "已完成"
        dl = task.deadline_date or task.scheduled_date
        if dl is None:
            return "无截止"
        days = (date.today() - dl).days
        if days > 0:
            return f"逾期{days}天"
        elif days == 0:
            return "今日截止"
        else:
            return f"剩余{-days}天"

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        for i, label in enumerate(self._carousel_labels):
            idx = self._scroll_index + i
            if idx < len(self._items):
                item = self._items[idx]
                label.setText(f"{item['urgency']}  {item['text']}")
                label.setToolTip(item["text"])
                label.setStyleSheet(
                    f"QLabel {{ padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; "
                    f"color: {item.get('label_color', get_tokens().text_primary)}; "
                    f"background: rgba(128,128,128,0.12); }}"
                )
                label.setVisible(True)
            else:
                label.setVisible(False)

    def _scroll(self) -> None:
        if not self._items:
            return
        self._scroll_index = (self._scroll_index + self._group_size) % max(len(self._items), 1)
        self._render()

    def _make_click_handler(self, i: int):
        def handler(event) -> None:
            idx = self._scroll_index + i
            if idx < len(self._items):
                self.task_clicked.emit(self._items[idx]["task_id"])
        return handler

    # ------------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------------

    def build_filter(self) -> TaskFilter:
        """Build a TaskFilter matching the active preset, sorted by urgency."""
        today = date.today()
        sort = [SortCriterion("urgency", ascending=True)]
        filter_ = TaskFilter(partition_id=self._partition_id, sort_by=sort)

        if self._active_preset == "yesterday":
            d = today - timedelta(days=1)
            filter_.date_from = d
            filter_.date_to = d
        elif self._active_preset == "today":
            filter_.date_from = today
            filter_.date_to = today
        elif self._active_preset == "last_week":
            last_monday = today - timedelta(days=today.isoweekday() + 6)
            last_sunday = last_monday + timedelta(days=6)
            filter_.date_from = last_monday
            filter_.date_to = last_sunday
        elif self._active_preset == "week":
            days_until_sunday = 7 - today.isoweekday()
            sunday = today + timedelta(days=days_until_sunday)
            monday = sunday - timedelta(days=6)
            filter_.date_from = monday
            filter_.date_to = sunday
        elif self._active_preset == "last_month":
            first_of_this_month = today.replace(day=1)
            last_day_of_last_month = first_of_this_month - timedelta(days=1)
            first_of_last_month = last_day_of_last_month.replace(day=1)
            filter_.date_from = first_of_last_month
            filter_.date_to = last_day_of_last_month
        elif self._active_preset == "month":
            import calendar as _cal
            _, last = _cal.monthrange(today.year, today.month)
            filter_.date_from = today.replace(day=1)
            filter_.date_to = today.replace(day=last)

        return filter_
