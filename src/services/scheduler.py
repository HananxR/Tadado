"""APScheduler-based service: overdue refresh + optional daily digest."""

from __future__ import annotations

from apscheduler.schedulers.qt import QtScheduler

from ..models.repository import TaskRepository
from ..utils.signal_bus import get_signal_bus


class TaskScheduler:
    """Periodically refreshes overdue status, plus an optional daily digest."""

    def __init__(self, repository: TaskRepository, config) -> None:
        self._repository = repository
        self._config = config
        self._signal_bus = get_signal_bus()
        self._scheduler = QtScheduler()

    def start(self) -> None:
        # Overdue refresh: every minute
        self._scheduler.add_job(
            self._check_due_tasks,
            "interval",
            minutes=1,
            id="overdue_refresh",
            replace_existing=True,
        )
        # Daily digest: at configured time
        digest_time = self._config.reminder_daily_digest_time or "09:00"
        try:
            h, m = map(int, digest_time.split(":"))
            self._scheduler.add_job(
                self._emit_daily_digest,
                "cron",
                hour=h,
                minute=m,
                id="daily_digest",
                replace_existing=True,
            )
        except (ValueError, AttributeError):
            pass
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def _check_due_tasks(self) -> None:
        """Auto-set/revert OVERDUE status for all tasks."""
        changed = self._repository.refresh_overdue_status()
        for task, old_status in changed:
            self._signal_bus.task_status_changed.emit(task, old_status)

    def _emit_daily_digest(self) -> None:
        """Emit daily digest signal (notifier handles the rest)."""
        self._signal_bus.daily_digest.emit()
