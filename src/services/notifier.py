"""Tray notification handler — listens to reminder_fired and shows tray messages."""

from __future__ import annotations

from datetime import datetime

from ..config import AppConfig
from ..models.task import Task
from ..utils.signal_bus import get_signal_bus


class TaskNotifier:
    """Listens to reminder_fired signals and shows system tray notifications,
    respecting quiet hours defined in config."""

    def __init__(self, tray_manager, config: AppConfig) -> None:
        self._tray = tray_manager
        self._config = config
        self._signal_bus = get_signal_bus()
        self._signal_bus.reminder_fired.connect(self._on_reminder_fired)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_reminder_fired(self, task: Task, interval_minutes: int) -> None:
        if self._in_quiet_hours():
            return

        title = "任务提醒"
        if interval_minutes >= 1440:
            msg = f"{task.title} — 截止日已超过 {interval_minutes // 1440} 天"
        elif interval_minutes >= 60:
            msg = f"{task.title} — 截止日还剩 {interval_minutes // 60} 小时"
        else:
            msg = f"{task.title} — 截止日还剩 {interval_minutes} 分钟"
        self._tray.show_message(title, msg)

    # ------------------------------------------------------------------
    # Quiet hours
    # ------------------------------------------------------------------

    def _in_quiet_hours(self) -> bool:
        try:
            start_str = self._config.get("reminders", "quiet_hours_start") or "22:00"
            end_str = self._config.get("reminders", "quiet_hours_end") or "08:00"
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
        except (ValueError, AttributeError):
            return False

        now = datetime.now().time()
        start = datetime.strptime(f"{start_h:02d}:{start_m:02d}", "%H:%M").time()
        end = datetime.strptime(f"{end_h:02d}:{end_m:02d}", "%H:%M").time()

        if start <= end:
            return start <= now <= end
        else:
            # Overnight range (e.g., 22:00–08:00)
            return now >= start or now <= end
