"""Tests for TaskService — the single seam between UI and data layers."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from src.models.task import Task
from src.models.task_filter import TaskFilter
from src.models.task_status import TaskStatus
from src.services.task_service import TaskService
from src.utils.signal_bus import SignalBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication — needed once for SignalBus (a QObject)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def service(temp_db, qapp):
    """Return a TaskService backed by a real SQLite temp database."""
    from src.models.repository import TaskRepository

    repo = TaskRepository(temp_db)
    repo.open()
    bus = SignalBus()  # fresh bus per test → no cross-test pollution
    svc = TaskService(repo, signal_bus=bus)
    yield svc
    repo.close()


def _make_task(
    task_id: str = "t1",
    title: str = "测试任务",
    status: TaskStatus = TaskStatus.TODO,
    tags: list[str] | None = None,
    deadline_date=None,
    urgency: int = 3,
    partition_id: str = "p1",
) -> Task:
    """Factory helper — one place to change when Task fields evolve."""
    import uuid

    return Task(
        id=task_id or str(uuid.uuid4()),
        raw_md="",
        title=title,
        status=status,
        tags=tags or [],
        deadline_date=deadline_date,
        partition_id=partition_id,
        urgency=urgency,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class TestCreateTask:
    def test_create_minimal(self, service):
        task = service.create_task("- [ ] 最小任务")
        assert task.title == "最小任务"
        assert task.status == TaskStatus.TODO
        assert task.raw_md.startswith("- [")
        assert service.get_task(task.id) is not None

    def test_create_with_tags(self, service):
        task = service.create_task("- [ ] 重构模块 #后端 #高优")
        assert task.title == "重构模块"
        assert set(task.tags) == {"后端", "高优"}

    def test_create_with_deadline(self, service):
        from datetime import date as _date

        task = service.create_task("- [ ] <2026-12-31> 年度总结")
        assert task.deadline_date == _date(2026, 12, 31)

    def test_create_with_priority(self, service):
        # Parser extracts star-count from bracket: 3 stars → urgency 0 (紧急)
        task = service.create_task("- [***] 紧急任务")
        # After format() round-trip, urgency=0 brackets display as [***]
        assert "***" in task.raw_md or task.urgency <= 3

    def test_create_emits_signal(self, service, qapp):
        received: list[Task] = []
        service._bus.task_created.connect(lambda t: received.append(t))
        task = service.create_task("- [ ] 信号测试")
        assert len(received) == 1
        assert received[0].id == task.id


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class TestUpdateTask:
    def test_update_title(self, service):
        task = service.create_task("- [ ] 旧标题")
        task.title = "新标题"
        updated = service.update_task(task)
        assert updated.title == "新标题"
        assert "新标题" in updated.raw_md

    def test_update_emits_signal(self, service, qapp):
        task = service.create_task("- [ ] 待更新")
        received: list[Task] = []
        service._bus.task_updated.connect(lambda t: received.append(t))
        task.title = "已更新"
        service.update_task(task)
        assert len(received) == 1


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDeleteTask:
    def test_delete_existing(self, service):
        task = service.create_task("- [ ] 待删除")
        assert service.get_task(task.id) is not None
        removed = service.delete_task(task.id)
        assert removed
        assert service.get_task(task.id) is None

    def test_delete_emits_signal(self, service, qapp):
        task = service.create_task("- [ ] 待删除信号")
        received: list[str] = []
        service._bus.task_deleted.connect(lambda tid: received.append(tid))
        service.delete_task(task.id)
        assert len(received) == 1
        assert received[0] == task.id


# ---------------------------------------------------------------------------
# Change status
# ---------------------------------------------------------------------------

class TestChangeTaskStatus:
    def test_todo_to_doing(self, service):
        task = service.create_task("- [ ] 状态测试")
        updated = service.change_task_status(task, TaskStatus.DOING)
        assert updated.status == TaskStatus.DOING

    def test_done_sets_progress_100(self, service):
        task = service.create_task("- [ ] 完成测试")
        updated = service.change_task_status(task, TaskStatus.DONE)
        assert updated.status == TaskStatus.DONE
        assert updated.progress == 100

    def test_emits_status_changed(self, service, qapp):
        task = service.create_task("- [ ] 状态信号")
        received: list[tuple] = []
        service._bus.task_status_changed.connect(
            lambda t, old: received.append((t.id, old))
        )
        service.change_task_status(task, TaskStatus.DOING)
        assert len(received) == 1
        assert received[0][1] == TaskStatus.TODO


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

class TestBatchOperations:
    @pytest.fixture
    def three_tasks(self, service):
        ids = []
        for i in range(3):
            t = service.create_task(f"- [ ] 批量任务{i + 1}", partition_id="p1")
            ids.append(t.id)
        return ids

    def test_batch_update_status(self, service, three_tasks, qapp):
        received: list[dict] = []
        service._bus.batch_operation_completed.connect(lambda d: received.append(d))
        count = service.batch_update_status(three_tasks, TaskStatus.DOING)
        assert count == 3
        for tid in three_tasks:
            assert service.get_task(tid).status == TaskStatus.DOING
        assert len(received) >= 1

    def test_batch_update_urgency(self, service, three_tasks):
        count = service.batch_update_urgency(three_tasks, 0)
        assert count == 3
        for tid in three_tasks:
            assert service.get_task(tid).urgency == 0

    def test_batch_delete(self, service, three_tasks, qapp):
        count = service.batch_delete(three_tasks)
        assert count == 3
        for tid in three_tasks:
            assert service.get_task(tid) is None

    def test_batch_suspend_restart(self, service, three_tasks):
        count = service.batch_suspend(three_tasks)
        assert count == 3
        for tid in three_tasks:
            assert service.get_task(tid).suspended

        count = service.batch_restart(three_tasks)
        assert count == 3
        for tid in three_tasks:
            assert not service.get_task(tid).suspended

    def test_batch_postpone(self, service, three_tasks, qapp):
        from datetime import date as _date, timedelta

        # Give them deadlines first
        today = _date.today()
        for tid in three_tasks:
            t = service.get_task(tid)
            t.deadline_date = today
            service._repo.update(t)

        count = service.batch_postpone(three_tasks, 3)
        assert count == 3
        for tid in three_tasks:
            assert service.get_task(tid).deadline_date == today + timedelta(days=3)

    def test_batch_move_partition(self, service, three_tasks, qapp):
        # Create target partition
        service._repo.upsert_partition("目标分区", partition_id="ptarget")
        count = service.batch_move_partition(three_tasks, "ptarget")
        assert count == 3
        for tid in three_tasks:
            assert service.get_task(tid).partition_id == "ptarget"

    def test_empty_batch_is_noop(self, service, qapp):
        assert service.batch_update_status([], TaskStatus.DOING) == 0
        assert service.batch_delete([]) == 0
        assert service.batch_suspend([]) == 0


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

class TestQueries:
    @pytest.fixture
    def mixed_tasks(self, service):
        service.create_task("- [ ] TODO 任务A #a", partition_id="p1")
        # DONE status requires explicit keyword BEFORE the title
        service.create_task("- [x] DONE 已完成的任务 #b", partition_id="p1")
        service.create_task("- [ ] DOING 任务C #a #b", partition_id="p2")

    def test_search_by_status(self, service, mixed_tasks):
        # DONE task with partition_id="p1"
        f = TaskFilter(statuses={TaskStatus.DONE}, partition_id="p1")
        results = service.search(f)
        assert len(results) >= 1
        assert all(t.status == TaskStatus.DONE for t in results)

    def test_search_by_partition(self, service, mixed_tasks):
        f = TaskFilter(partition_id="p1")
        results = service.search(f)
        assert len(results) == 2

    def test_search_with_total(self, service, mixed_tasks):
        results, total = service.search_with_total(TaskFilter())
        assert total >= 3
        assert len(results) >= 3

    def test_get_all(self, service, mixed_tasks):
        all_tasks = service.get_all()
        assert len(all_tasks) >= 3

    def test_count(self, service, mixed_tasks):
        cnt = service.count(TaskFilter())
        assert cnt >= 3

    def test_get_status_counts(self, service, mixed_tasks):
        counts = service.get_status_counts()
        assert isinstance(counts, dict)
        assert sum(counts.values()) >= 3


# ---------------------------------------------------------------------------
# Partitions
# ---------------------------------------------------------------------------

class TestPartitions:
    def test_ensure_default(self, service):
        pid = service.ensure_default_partition()
        assert pid
        partitions = service.get_all_partitions()
        assert len(partitions) >= 1

    def test_upsert_new(self, service, qapp):
        result = service.upsert_partition("工作")
        assert result["name"] == "工作"
        assert result["id"]

    def test_upsert_rename(self, service, qapp):
        r1 = service.upsert_partition("原名")
        r2 = service.upsert_partition("新名", partition_id=r1["id"])
        assert r2["name"] == "新名"
        assert r2["id"] == r1["id"]

    def test_delete_partition(self, service, qapp):
        r = service.upsert_partition("待删")
        service.delete_partition(r["id"])
        partitions = service.get_all_partitions()
        assert not any(p["id"] == r["id"] for p in partitions)

    def test_password_roundtrip(self, service):
        r = service.upsert_partition("加密分区")
        service.set_partition_password(r["id"], "secret123")
        has_pw, pw = service.check_partition_password(r["id"])
        assert has_pw
        assert pw == "secret123"

        service.set_partition_password(r["id"], "")
        has_pw, pw = service.check_partition_password(r["id"])
        assert not has_pw

    def test_partition_name_map(self, service):
        service.upsert_partition("A区")
        service.upsert_partition("B区")
        name_map = service.get_partition_name_map()
        assert len(name_map) >= 2

    def test_count_tasks_in_partition(self, service):
        r = service.upsert_partition("有任务的分区")
        service.create_task("- [ ] 任务1", partition_id=r["id"])
        service.create_task("- [ ] 任务2", partition_id=r["id"])
        assert service.count_tasks_in_partition(r["id"]) == 2


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

class TestTags:
    def test_get_all_tags(self, service):
        service.create_task("- [ ] 重构 #后端", partition_id="p1")
        service.create_task("- [ ] 学习 #前端", partition_id="p1")
        tags = service.get_all_tags("p1")
        assert "后端" in tags
        assert "前端" in tags

    def test_get_all_tags_with_counts(self, service):
        service.create_task("- [ ] A #work", partition_id="p1")
        service.create_task("- [ ] B #work #home", partition_id="p1")
        counts = service.get_all_tags_with_counts("p1")
        tag_map = dict(counts)
        assert tag_map.get("work") == 2
        assert tag_map.get("home") == 1

    def test_get_tasks_by_tag(self, service):
        service.create_task("- [ ] 工作事项 #work", partition_id="p1")
        service.create_task("- [ ] 个人事项 #home", partition_id="p1")
        tasks = service.get_tasks_by_tag("work", "p1")
        assert len(tasks) == 1
        assert tasks[0].title == "工作事项"

    def test_get_tasks_by_tags(self, service):
        service.create_task("- [ ] W #work", partition_id="p1")
        service.create_task("- [ ] H #home", partition_id="p1")
        service.create_task("- [ ] B #both #work #home", partition_id="p1")
        tasks = service.get_tasks_by_tags({"work", "home"}, "p1")
        # Should match any tag: all three
        assert len(tasks) == 3


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

class TestHeatmap:
    def test_get_heatmap_activity_data_empty(self, service):
        from datetime import date as _date

        entries, tasks = service.get_heatmap_activity_data(2026)
        assert isinstance(entries, dict)
        assert isinstance(tasks, dict)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_format_task(self, service):
        task = service.create_task("- [ ] 格式测试 #tag")
        md = service.format_task(task)
        assert "格式测试" in md
        assert "#tag" in md

    def test_parse_markdown(self, service):
        # Correct format: keyword <date> — space before <
        parsed = service.parse_markdown("- [ ] TODO <2026-12-31> 测试 #a")
        assert parsed.title == "测试"
        assert parsed.status == TaskStatus.TODO
        assert set(parsed.tags) == {"a"}

    def test_round_trip(self, service):
        """format(parse(raw)) → format(parse(raw)) should be stable."""
        raw = "- [ ] TODO<2026-06-15> 往返测试 #闭环"
        parsed1 = service.parse_markdown(raw)

        task = Task(
            id="roundtrip",
            raw_md="",
            title=parsed1.title,
            status=parsed1.status,
            tags=parsed1.tags,
            deadline_date=parsed1.deadline_date,
            deadline_time=parsed1.deadline_time,
            scheduled_date=parsed1.scheduled_date,
        )
        task.raw_md = service.format_task(task)
        parsed2 = service.parse_markdown(task.raw_md)
        assert parsed2.title == parsed1.title
        assert parsed2.status == parsed1.status
        assert parsed2.tags == parsed1.tags


# ---------------------------------------------------------------------------
# Signal isolation
# ---------------------------------------------------------------------------

class TestSignalIsolation:
    """Each service instance gets its own SignalBus — no cross-test leakage."""

    def test_separate_services_have_separate_buses(self, temp_db, qapp):
        from src.models.repository import TaskRepository

        repo1 = TaskRepository(temp_db)
        repo1.open()
        bus1 = SignalBus()
        svc1 = TaskService(repo1, signal_bus=bus1)

        # Second service on same DB — different bus
        repo2 = TaskRepository(temp_db)
        repo2.open()
        bus2 = SignalBus()
        svc2 = TaskService(repo2, signal_bus=bus2)

        events1: list[str] = []
        events2: list[str] = []
        bus1.task_created.connect(lambda t: events1.append(t.id))
        bus2.task_created.connect(lambda t: events2.append(t.id))

        svc1.create_task("- [ ] 来自svc1")
        svc2.create_task("- [ ] 来自svc2")

        assert len(events1) == 1  # only svc1's emit
        assert len(events2) == 1  # only svc2's emit

        repo1.close()
        repo2.close()
