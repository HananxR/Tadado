"""APScheduler-based service: overdue refresh + optional daily digest."""

from __future__ import annotations

import logging

from apscheduler.schedulers.qt import QtScheduler

from ..models.repository import TaskRepository
from ..utils.signal_bus import get_signal_bus

_log = logging.getLogger("runlog")


class TaskScheduler:
    """Periodically refreshes overdue status, plus an optional daily digest."""

    def __init__(
        self, repository: TaskRepository, config,
        task_service=None, scheduler=None, signal_bus=None,
    ) -> None:
        self._repository = repository
        self._task_service = task_service
        self._config = config
        self._signal_bus = signal_bus or get_signal_bus()
        self._scheduler = scheduler or QtScheduler()

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
        except (ValueError, AttributeError) as exc:
            _log.warning("Failed to parse digest time '%s': %s", digest_time, exc)
        self._scheduler.start()
        _log.info("Scheduler started: overdue refresh every 60s, digest at %s", digest_time)

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            _log.info("Scheduler stopped")

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def _check_due_tasks(self) -> None:
        """Auto-set/revert OVERDUE status for all tasks."""
        if self._task_service:
            changed = self._task_service.refresh_overdue_status()
        else:
            changed = self._repository.refresh_overdue_status()
            if changed:
                for task, old_status in changed:
                    self._signal_bus.task_status_changed.emit(task, old_status)
            return
        if changed:
            _log.info("Overdue check: %s tasks changed", len(changed))

    def _emit_daily_digest(self) -> None:
        """Emit daily digest signal (notifier handles the rest)."""
        self._signal_bus.daily_digest.emit()
