"""Automatic archiver for completed tasks older than the configured threshold."""

from __future__ import annotations

from datetime import date, timedelta

from apscheduler.schedulers.qt import QtScheduler

from ..config import AppConfig
from ..models.repository import TaskRepository
from ..utils.signal_bus import get_signal_bus


class TaskArchiver:
    """Periodically archives completed tasks after the configured number of days."""

    def __init__(self, repository: TaskRepository, config: AppConfig) -> None:
        self._repository = repository
        self._config = config
        self._signal_bus = get_signal_bus()
        self._scheduler = QtScheduler()

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_archive,
            "cron",
            hour=0,
            minute=0,
            id="archive_check",
            replace_existing=True,
        )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _run_archive(self) -> None:
        today = date.today()
        partitions = self._repository.get_all_partitions()
        total_archived = 0

        for p in partitions:
            if not p.get("archive_enabled", 0):
                continue
            archive_days = p.get("archive_days", 9999)
            if archive_days >= 9999:
                continue  # never archive
            cutoff = today - timedelta(days=archive_days)
            tasks = self._repository.get_tasks_for_archive(cutoff, p["id"])
            if tasks:
                ids = [t.id for t in tasks]
                total_archived += self._repository.archive_batch(ids)

        if total_archived:
            self._signal_bus.archive_completed.emit(total_archived)
