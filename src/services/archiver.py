"""Automatic archiver for completed tasks older than the configured threshold."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.qt import QtScheduler

from ..config import AppConfig
from ..models.repository import TaskRepository
from ..utils.signal_bus import get_signal_bus

_log = logging.getLogger("runlog")


class TaskArchiver:
    """Periodically archives completed tasks after the configured number of days."""

    def __init__(
        self, repository: TaskRepository, config: AppConfig,
        scheduler=None, signal_bus=None,
    ) -> None:
        self._repository = repository
        self._config = config
        self._signal_bus = signal_bus or get_signal_bus()
        self._scheduler = scheduler or QtScheduler()

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
        _log.info("Archiver started (midnight cron)")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            _log.info("Archiver stopped")

    def _run_archive(self) -> None:
        today = date.today()
        partitions = self._repository.get_all_partitions()
        total_archived = 0

        for p in partitions:
            archive_days = p.get("archive_days", 0)
            if archive_days >= 9999 or archive_days <= 0:
                continue  # 9999=never, 0=immediate (handled by TaskService)
            cutoff = today - timedelta(days=archive_days)
            tasks = self._repository.get_tasks_for_archive(cutoff, p["id"])
            if tasks:
                ids = [t.id for t in tasks]
                count = self._repository.archive_batch(ids)
                total_archived += count
                _log.info("  Partition %s: %s archived", p["name"], count)

        if total_archived:
            _log.info("Archive run complete: %s tasks across %s partitions", total_archived, len(partitions))
            self._signal_bus.archive_completed.emit(total_archived)
