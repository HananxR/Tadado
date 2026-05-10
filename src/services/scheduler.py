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
        if not self._config.reminders_enabled:
            return

        due = self._repository.get_due_today()
        overdue = self._repository.get_overdue()
        intervals = self._config.reminder_intervals

        for task in due + overdue:
            for interval in intervals:
                if not self._repository.notification_sent(task.id, interval):
                    self._signal_bus.reminder_fired.emit(task, interval)
                    self._repository.mark_notification_sent(task.id, interval)
