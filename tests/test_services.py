"""Tests for background services — made testable via dependency injection."""

from __future__ import annotations

from datetime import date as _date, datetime as _datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.models.task import Task
from src.models.task_status import TaskStatus
from src.services.archiver import TaskArchiver
from src.services.scheduler import TaskScheduler


# ---------------------------------------------------------------------------
# Fake scheduler for testing
# ---------------------------------------------------------------------------

class FakeScheduler:
    """A fake APScheduler-compatible scheduler that records jobs."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.running = True

    def add_job(self, func, trigger, **kwargs):
        job_id = kwargs.get("id", str(len(self.jobs)))
        args = kwargs.get("args", ())
        self.jobs[job_id] = {"func": func, "trigger": trigger, "args": args, "kwargs": kwargs}
        return MagicMock(id=job_id)

    def start(self):
        self.running = True

    def shutdown(self, wait=False):
        self.running = False


# ---------------------------------------------------------------------------
# Fake SignalBus for testing
# ---------------------------------------------------------------------------

class FakeSignalBus:
    """Signal bus stub with auto-created MagicMock signal attributes."""

    def __init__(self):
        self._signals: dict[str, MagicMock] = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._signals:
            self._signals[name] = MagicMock()
        return self._signals[name]


# ---------------------------------------------------------------------------
# TaskScheduler tests
# ---------------------------------------------------------------------------

class TestTaskScheduler:
    @pytest.fixture
    def scheduler(self, temp_db, qapp):
        from src.models.repository import TaskRepository
        from src.config import AppConfig

        repo = TaskRepository(temp_db)
        repo.open()
        config = AppConfig()
        fake_sched = FakeScheduler()
        fake_bus = FakeSignalBus()
        svc = TaskScheduler(
            repo, config, scheduler=fake_sched, signal_bus=fake_bus,
        )
        yield svc, repo, fake_sched, fake_bus
        repo.close()

    def test_start_adds_jobs(self, scheduler):
        svc, repo, fake_sched, fake_bus = scheduler
        svc.start()
        assert "overdue_refresh" in fake_sched.jobs
        assert "daily_digest" in fake_sched.jobs
        assert fake_sched.running

    def test_stop_shuts_down(self, scheduler):
        svc, repo, fake_sched, fake_bus = scheduler
        svc.start()
        svc.stop()
        assert not fake_sched.running

    def test_overdue_check_with_tasks(self, scheduler):
        svc, repo, fake_sched, fake_bus = scheduler
        # Create a task with yesterday's deadline
        yesterday = _date.today() - timedelta(days=1)
        task = Task(
            id="t1", raw_md="- [ ] 逾期任务", title="逾期任务",
            status=TaskStatus.TODO,
            deadline_date=yesterday,
        )
        repo.insert(task)

        # Manually trigger overdue check
        svc._check_due_tasks()
        updated = repo.get_by_id("t1")
        assert updated is not None
        assert updated.status == TaskStatus.OVERDUE

    def test_daily_digest_emits_signal(self, scheduler):
        svc, repo, fake_sched, fake_bus = scheduler
        svc._emit_daily_digest()
        fake_bus.daily_digest.emit.assert_called_once()

    def test_check_due_tasks_with_task_service(self, temp_db, qapp):
        """Scheduler uses TaskService for overdue refresh when available."""
        from src.models.repository import TaskRepository
        from src.services.task_service import TaskService
        from src.config import AppConfig

        repo = TaskRepository(temp_db)
        repo.open()
        svc = TaskService(repo)
        config = AppConfig()
        sched = TaskScheduler(
            repo, config, task_service=svc,
            scheduler=FakeScheduler(), signal_bus=FakeSignalBus(),
        )

        yesterday = _date.today() - timedelta(days=1)
        svc.create_task("- [ ] 逾期任务", partition_id="p1")
        # Manually set deadline to yesterday
        from src.models.task_filter import TaskFilter
        task = repo.search(TaskFilter(partition_id="p1"))[0]
        # The task was just created today, we need to force the test
        # Actually, the repository's refresh_overdue_status scans by deadline_date
        repo.conn.execute(
            "UPDATE tasks SET deadline_date=? WHERE id=?",
            (yesterday.isoformat(), task.id),
        )
        repo.conn.commit()

        sched._check_due_tasks()
        updated = repo.get_by_id(task.id)
        assert updated.status == TaskStatus.OVERDUE
        repo.close()


# ---------------------------------------------------------------------------
# TaskArchiver tests
# ---------------------------------------------------------------------------

class TestTaskArchiver:
    @pytest.fixture
    def archiver(self, temp_db, qapp):
        from src.models.repository import TaskRepository
        from src.config import AppConfig

        repo = TaskRepository(temp_db)
        repo.open()
        config = AppConfig()
        fake_sched = FakeScheduler()
        fake_bus = FakeSignalBus()
        svc = TaskArchiver(
            repo, config, scheduler=fake_sched, signal_bus=fake_bus,
        )
        yield svc, repo, fake_sched, fake_bus
        repo.close()

    def test_start_adds_archive_job(self, archiver):
        svc, repo, fake_sched, fake_bus = archiver
        svc.start()
        assert "archive_check" in fake_sched.jobs
        assert fake_sched.running

    def test_stop_shuts_down(self, archiver):
        svc, repo, fake_sched, fake_bus = archiver
        svc.start()
        svc.stop()
        assert not fake_sched.running

    def test_run_archive_with_completed_task(self, archiver):
        svc, repo, fake_sched, fake_bus = archiver
        # Create a DONE task completed long ago
        from src.services.task_service import TaskService

        tsvc = TaskService(repo)
        task = tsvc.create_task("- [ ] 待归档", partition_id="p1")
        # Set as DONE with old completed_at
        repo.conn.execute(
            "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
            ("DONE", (_date.today() - timedelta(days=10)).isoformat(), task.id),
        )
        repo.conn.commit()

        # Create a partition with archive_days=7
        pid = repo.upsert_partition("测试分区")["id"]
        repo.conn.execute(
            "UPDATE partitions SET archive_enabled=1, archive_days=7 WHERE id=?",
            (pid,),
        )
        repo.conn.execute(
            "UPDATE tasks SET partition_id=? WHERE id=?",
            (pid, task.id),
        )
        repo.conn.commit()

        svc._run_archive()
        updated = repo.get_by_id(task.id)
        assert updated is not None
        assert updated.archived

    def test_archive_emits_signal(self, archiver):
        svc, repo, fake_sched, fake_bus = archiver
        from src.services.task_service import TaskService

        tsvc = TaskService(repo)
        task = tsvc.create_task("- [ ] 待归档2", partition_id="p1")
        pid = repo.upsert_partition("测试分区2")["id"]
        repo.conn.execute(
            "UPDATE partitions SET archive_enabled=1, archive_days=1 WHERE id=?",
            (pid,),
        )
        repo.conn.execute(
            "UPDATE tasks SET status='DONE', completed_at=?, partition_id=? WHERE id=?",
            ((_date.today() - timedelta(days=2)).isoformat(), pid, task.id),
        )
        repo.conn.commit()

        # Track archive_completed signal
        archive_counts = []
        fake_bus.archive_completed = MagicMock()
        fake_bus.archive_completed.emit = lambda c: archive_counts.append(c)

        svc._run_archive()
        assert len(archive_counts) >= 1
        assert archive_counts[0] >= 1
