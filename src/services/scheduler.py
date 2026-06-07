"""APScheduler-based service that periodically checks for due tasks."""

from __future__ import annotations

from apscheduler.schedulers.qt import QtScheduler

from ..models.repository import TaskRepository
from ..utils.signal_bus import get_signal_bus


class TaskScheduler:
    """Checks for due/overdue tasks every minute and emits reminder signals."""

    def __init__(self, repository: TaskRepository, config) -> None:
        self._repository = repository
        self._config = config
        self._signal_bus = get_signal_bus()
        self._scheduler = QtScheduler()

    def start(self) -> None:
        self._scheduler.add_job(
            self._check_due_tasks,
            "interval",
            minutes=1,
            id="reminder_check",
            replace_existing=True,
        )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def _check_due_tasks(self) -> None:
        # Phase 1: Auto-set/revert OVERDUE status (always runs)
        changed = self._repository.refresh_overdue_status()
        for task, old_status in changed:
            self._signal_bus.task_status_changed.emit(task, old_status)

        # Phase 2: Reminder check (respects reminders_enabled)
        if not self._config.reminders_enabled:
            return

        pid = self._config.get("general", "last_partition_id", default="") or None
        due = self._repository.get_due_today(partition_id=pid)
        overdue = self._repository.get_overdue(partition_id=pid)
        intervals = self._config.reminder_intervals

        reminders: list = []
        for task in due + overdue:
            for interval in intervals:
                if not self._repository.notification_sent(task.id, interval):
                    reminders.append((task, interval))
                    self._repository.mark_notification_sent(task.id, interval)
        if reminders:
            self._signal_bus.reminders_fired.emit(reminders)
