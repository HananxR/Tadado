"""后台服务测试（#5 Service 去 Qt 耦合）。

这 4 个后台服务此前在构造时硬编码 ``QtScheduler()``、直连 ``SignalBus`` 单例，
导致无 QApplication 时无法实例化 —— 长期零测试覆盖。现已全部支持构造注入，
用轻量桩替身即可覆盖其纯逻辑（调度注册、归档阈值、循环克隆、摘要通知）。

注入点一览：

===============  ==========================================
服务              注入参数
===============  ==========================================
TaskScheduler    scheduler / signal_bus / task_service
TaskArchiver     scheduler / signal_bus
TaskRecurrence   signal_bus
TaskNotifier     signal_bus
===============  ==========================================
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.config import AppConfig
from src.models.task import Task
from src.models.task_status import TaskStatus
from src.services.archiver import TaskArchiver
from src.services.notifier import TaskNotifier
from src.services.recurrence import TaskRecurrence
from src.services.scheduler import TaskScheduler
from src.services.task_service import TaskService
from src.utils.signal_bus import SignalBus


class _StubScheduler:
    """调度器替身：记录 ``add_job``，不启动任何线程或事件循环。"""

    def __init__(self) -> None:
        self.jobs: list[tuple] = []
        self.running = False
        self.shutdown_calls = 0

    def add_job(self, func, trigger, **kwargs) -> None:
        self.jobs.append((func, trigger, kwargs))

    def start(self) -> None:
        self.running = True

    def shutdown(self, wait: bool = False) -> None:
        self.running = False
        self.shutdown_calls += 1

    def job_ids(self) -> list[str]:
        return [kw.get("id") for _func, _trigger, kw in self.jobs]


class _StubTray:
    """托盘替身：记录 ``show_message`` 调用。"""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def show_message(self, title: str, msg: str) -> None:
        self.messages.append((title, msg))


@pytest.fixture
def bus() -> SignalBus:
    """每个用例独立信号总线，避免跨用例污染。"""
    return SignalBus()


@pytest.fixture
def config(tmp_path) -> AppConfig:
    return AppConfig(tmp_path)


@pytest.fixture
def svc(repository, bus, qapp) -> TaskService:
    service = TaskService(repository, signal_bus=bus)
    yield service
    service.dispose()


@pytest.fixture
def pid(svc) -> str:
    return svc.ensure_default_partition()


def _done_task(title: str, completed: date, pid: str) -> Task:
    """已完成任务（直接落库，跳过 service 的即时归档逻辑）。"""
    now = datetime.now()
    return Task(
        id=f"done-{title}",
        raw_md=f"- [x] {title}",
        title=title,
        status=TaskStatus.DONE,
        partition_id=pid,
        completed_at=completed,
        created_at=now,
        updated_at=now,
    )


def _due_task(title: str, deadline: date, pid: str) -> Task:
    """今日到期任务。"""
    now = datetime.now()
    return Task(
        id=f"due-{title}",
        raw_md=f"- [ ] {title}",
        title=title,
        status=TaskStatus.TODO,
        partition_id=pid,
        deadline_date=deadline,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# TaskScheduler
# ---------------------------------------------------------------------------


class TestTaskScheduler:
    def test_start_registers_overdue_and_digest_jobs(self, repository, config, bus, svc):
        sched = _StubScheduler()
        scheduler = TaskScheduler(
            repository, config, task_service=svc, scheduler=sched, signal_bus=bus
        )

        scheduler.start()

        assert sched.job_ids() == ["overdue_refresh", "daily_digest"]
        assert sched.running is True

    def test_stop_shuts_down_when_running(self, repository, config, bus, svc):
        sched = _StubScheduler()
        scheduler = TaskScheduler(
            repository, config, task_service=svc, scheduler=sched, signal_bus=bus
        )

        scheduler.start()
        scheduler.stop()

        assert sched.shutdown_calls == 1
        assert sched.running is False

    def test_stop_is_noop_when_not_started(self, repository, config, bus, svc):
        sched = _StubScheduler()
        scheduler = TaskScheduler(
            repository, config, task_service=svc, scheduler=sched, signal_bus=bus
        )

        scheduler.stop()

        assert sched.shutdown_calls == 0

    def test_check_due_tasks_delegates_to_task_service(self, repository, config, bus):
        """有 task_service 时由它负责状态刷新与信号（避免重复发信号）。"""
        calls: list[int] = []

        class _FakeService:
            def refresh_overdue_status(self):
                calls.append(1)
                return []

        scheduler = TaskScheduler(
            repository, config, task_service=_FakeService(),
            scheduler=_StubScheduler(), signal_bus=bus,
        )

        scheduler._check_due_tasks()

        assert calls == [1]

    def test_emit_daily_digest_emits_signal(self, repository, config, bus):
        received: list[int] = []
        bus.daily_digest.connect(lambda: received.append(1))
        scheduler = TaskScheduler(
            repository, config, scheduler=_StubScheduler(), signal_bus=bus
        )

        scheduler._emit_daily_digest()

        assert received == [1]

    def test_invalid_digest_time_skips_only_that_job(self, repository, config, bus):
        """摘要时间配置非法时只跳过摘要 job，逾期刷新仍照常注册。"""
        config.set("reminders", "daily_digest_time", value="not-a-time")
        sched = _StubScheduler()
        scheduler = TaskScheduler(
            repository, config, scheduler=sched, signal_bus=bus
        )

        scheduler.start()

        assert "overdue_refresh" in sched.job_ids()
        assert "daily_digest" not in sched.job_ids()


# ---------------------------------------------------------------------------
# TaskArchiver
# ---------------------------------------------------------------------------


class TestTaskArchiver:
    def test_skips_immediate_archive_partition(self, repository, config, bus, pid):
        """archive_days=0（即时归档）由 TaskService 负责，归档器须跳过。"""
        repository.insert(_done_task("即时归档", date.today() - timedelta(days=30), pid))
        assert repository.get_all_partitions()[0]["archive_days"] == 0

        archiver = TaskArchiver(
            repository, config, scheduler=_StubScheduler(), signal_bus=bus
        )
        archiver._run_archive()

        assert not any(t.archived for t in repository.get_all())

    def test_archives_only_tasks_past_threshold(self, repository, config, bus, pid):
        repository.update_partition_archive_days(pid, 3)
        old = _done_task("陈旧", date.today() - timedelta(days=10), pid)
        fresh = _done_task("新近", date.today(), pid)
        repository.insert(old)
        repository.insert(fresh)

        received: list[int] = []
        bus.archive_completed.connect(lambda n: received.append(n))

        archiver = TaskArchiver(
            repository, config, scheduler=_StubScheduler(), signal_bus=bus
        )
        archiver._run_archive()

        archived = {t.id for t in repository.get_all() if t.archived}
        assert old.id in archived
        assert fresh.id not in archived
        assert received == [1]

    def test_never_archive_partition_is_skipped(self, repository, config, bus, pid):
        """9999 = 永不归档。"""
        repository.update_partition_archive_days(pid, 9999)
        repository.insert(_done_task("永久保留", date.today() - timedelta(days=999), pid))

        archiver = TaskArchiver(
            repository, config, scheduler=_StubScheduler(), signal_bus=bus
        )
        archiver._run_archive()

        assert not any(t.archived for t in repository.get_all())

    def test_stop_shuts_down(self, repository, config, bus):
        sched = _StubScheduler()
        archiver = TaskArchiver(repository, config, scheduler=sched, signal_bus=bus)

        archiver.start()
        archiver.stop()

        assert sched.shutdown_calls == 1


# ---------------------------------------------------------------------------
# TaskRecurrence
# ---------------------------------------------------------------------------


class TestTaskRecurrence:
    def test_done_recurring_task_creates_next_instance(self, repository, bus):
        handler = TaskRecurrence(repository, signal_bus=bus)  # noqa: F841 — 需保活
        created: list[Task] = []
        bus.task_created.connect(lambda t: created.append(t))

        task = Task(
            id="r1",
            raw_md="- [ ] 周报 +1w",
            title="周报",
            status=TaskStatus.DONE,
            recurrence_rule="+1w",
            scheduled_date=date(2026, 9, 7),
            deadline_date=date(2026, 9, 14),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        repository.insert(task)

        bus.task_status_changed.emit(task, TaskStatus.DOING)

        assert len(created) == 1
        clone = created[0]
        assert clone.status == TaskStatus.TODO
        assert clone.title == "周报"
        assert clone.recurrence_rule == "+1w"
        assert clone.scheduled_date == date(2026, 9, 14)
        assert clone.deadline_date == date(2026, 9, 21)
        assert clone.id != task.id

    def test_non_recurring_task_is_ignored(self, repository, bus):
        handler = TaskRecurrence(repository, signal_bus=bus)  # noqa: F841
        created: list[Task] = []
        bus.task_created.connect(lambda t: created.append(t))

        task = Task(
            id="n1", raw_md="- [ ] 普通任务", title="普通任务",
            status=TaskStatus.DONE,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        repository.insert(task)

        bus.task_status_changed.emit(task, TaskStatus.DOING)

        assert created == []

    def test_transition_from_done_is_ignored(self, repository, bus):
        """DONE → 其他 的变更不是「刚完成」，不应触发克隆。"""
        handler = TaskRecurrence(repository, signal_bus=bus)  # noqa: F841
        created: list[Task] = []
        bus.task_created.connect(lambda t: created.append(t))

        task = Task(
            id="n2", raw_md="- [ ] 周报 +1w", title="周报",
            status=TaskStatus.DOING, recurrence_rule="+1w",
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        repository.insert(task)

        bus.task_status_changed.emit(task, TaskStatus.DONE)

        assert created == []

    @pytest.mark.parametrize(
        "rule,expected_days",
        [("+1d", 1), ("+3d", 3), ("+1w", 7)],
    )
    def test_rule_offsets(self, repository, bus, rule, expected_days):
        created: list[Task] = []
        bus.task_created.connect(lambda t: created.append(t))
        handler = TaskRecurrence(repository, signal_bus=bus)  # noqa: F841

        base = date(2026, 9, 14)
        task = Task(
            id=f"r-{rule}", raw_md=f"- [ ] 循环 {rule}", title="循环",
            status=TaskStatus.DONE, recurrence_rule=rule,
            deadline_date=base,
            created_at=datetime.now(), updated_at=datetime.now(),
        )
        repository.insert(task)

        bus.task_status_changed.emit(task, TaskStatus.DOING)

        assert len(created) == 1
        assert created[0].deadline_date == base + timedelta(days=expected_days)


# ---------------------------------------------------------------------------
# TaskNotifier
# ---------------------------------------------------------------------------


class TestTaskNotifier:
    def test_disabled_reminders_do_nothing(self, repository, config, bus, pid):
        tray = _StubTray()
        TaskNotifier(tray, config, repository, signal_bus=bus)  # noqa: F841

        bus.daily_digest.emit()

        assert tray.messages == []

    def test_no_due_tasks_shows_nothing(self, repository, config, bus, pid):
        config.set("reminders", "enabled", value=True)
        tray = _StubTray()
        notifier = TaskNotifier(tray, config, repository, signal_bus=bus)
        notifier._in_quiet_hours = lambda: False

        notifier._on_daily_digest()

        assert tray.messages == []

    def test_digest_shows_merged_message(self, repository, config, bus, pid):
        config.set("reminders", "enabled", value=True)
        repository.insert(_due_task("今日截止", date.today(), pid))

        tray = _StubTray()
        notifier = TaskNotifier(tray, config, repository, signal_bus=bus)
        notifier._in_quiet_hours = lambda: False

        notifier._on_daily_digest()

        assert len(tray.messages) == 1
        title, msg = tray.messages[0]
        assert title == "Tadado 每日摘要"
        assert "今日到期 1 项" in msg
        assert "今日截止" in msg

    def test_quiet_hours_silences_digest(self, repository, config, bus, pid):
        config.set("reminders", "enabled", value=True)
        repository.insert(_due_task("今日截止", date.today(), pid))

        tray = _StubTray()
        notifier = TaskNotifier(tray, config, repository, signal_bus=bus)
        notifier._in_quiet_hours = lambda: True

        notifier._on_daily_digest()

        assert tray.messages == []

    def test_overdue_and_due_are_merged(self, repository, config, bus, pid):
        config.set("reminders", "enabled", value=True)
        repository.insert(_due_task("今天到期", date.today(), pid))
        repository.insert(_due_task("已经逾期", date.today() - timedelta(days=3), pid))

        tray = _StubTray()
        notifier = TaskNotifier(tray, config, repository, signal_bus=bus)
        notifier._in_quiet_hours = lambda: False

        notifier._on_daily_digest()

        assert len(tray.messages) == 1
        _title, msg = tray.messages[0]
        assert "逾期 1 项" in msg
        assert "今日到期 1 项" in msg
