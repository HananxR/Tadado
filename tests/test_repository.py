"""Tests for TaskRepository."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from src.models.repository import TaskRepository
from src.models.task import Task
from src.models.task_filter import SortCriterion, TaskFilter
from src.models.task_status import TaskStatus


def _make_task(
    task_id: str | None = None,
    title: str = "测试任务",
    status: TaskStatus = TaskStatus.TODO,
    tags: list[str] | None = None,
    deadline_date: date | None = None,
    scheduled_date: date | None = None,
    archived: bool = False,
    progress: int = 0,
    urgency: int = 3,
) -> Task:
    now = datetime.now()
    return Task(
        id=task_id or str(uuid.uuid4()),
        raw_md=f"- [{'x' if status == TaskStatus.DONE else ' '}] {status.value} {title}",
        title=title,
        status=status,
        tags=tags or [],
        scheduled_date=scheduled_date,
        deadline_date=deadline_date,
        urgency=urgency,
        created_at=now,
        updated_at=now,
        archived=archived,
        progress=progress,
    )


class TestCRUD:
    def test_insert_and_get(self, repository: TaskRepository) -> None:
        task = _make_task(title="买菜")
        inserted = repository.insert(task)
        assert inserted.id

        fetched = repository.get_by_id(inserted.id)
        assert fetched is not None
        assert fetched.title == "买菜"
        assert fetched.raw_md == task.raw_md

    def test_update(self, repository: TaskRepository) -> None:
        task = _make_task(title="旧标题")
        inserted = repository.insert(task)

        inserted.title = "新标题"
        inserted.status = TaskStatus.DONE
        repository.update(inserted)

        fetched = repository.get_by_id(inserted.id)
        assert fetched is not None
        assert fetched.title == "新标题"
        assert fetched.status == TaskStatus.DONE

    def test_delete(self, repository: TaskRepository) -> None:
        task = repository.insert(_make_task())
        assert repository.delete(task.id) is True
        assert repository.get_by_id(task.id) is None
        assert repository.delete("nonexistent") is False


class TestSearch:
    def test_search_all(self, repository: TaskRepository) -> None:
        for i in range(5):
            repository.insert(_make_task(task_id=str(i), title=f"任务{i}"))
        results = repository.search(TaskFilter(show_archived=True))
        assert len(results) == 5

    def test_hide_archived(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="a", title="active"))
        repository.insert(_make_task(task_id="b", title="archived", archived=True))
        results = repository.search(TaskFilter())
        assert len(results) == 1
        assert results[0].id == "a"

    def test_search_text(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(title="买苹果"))
        repository.insert(_make_task(title="买香蕉"))
        repository.insert(_make_task(title="写代码"))
        results = repository.search(TaskFilter(search_text="香蕉"))
        assert len(results) == 1
        assert results[0].title == "买香蕉"

    def test_status_filter(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="1", status=TaskStatus.TODO))
        repository.insert(_make_task(task_id="2", status=TaskStatus.DONE))
        repository.insert(_make_task(task_id="3", status=TaskStatus.DOING))
        results = repository.search(TaskFilter(statuses={TaskStatus.TODO, TaskStatus.DOING}))
        assert len(results) == 2
        statuses = {r.status for r in results}
        assert statuses == {TaskStatus.TODO, TaskStatus.DOING}

    def test_sorting(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="1", title="C任务"))
        repository.insert(_make_task(task_id="2", title="A任务"))
        repository.insert(_make_task(task_id="3", title="B任务"))
        results = repository.search(
            TaskFilter(sort_by=[SortCriterion("title", ascending=True)])
        )
        assert [r.title for r in results] == ["A任务", "B任务", "C任务"]

    def test_limit_offset(self, repository: TaskRepository) -> None:
        for i in range(10):
            repository.insert(_make_task(task_id=str(i), title=f"任务{i}"))
        results = repository.search(TaskFilter(limit=3, offset=2))
        assert len(results) == 3


class TestAggregations:
    def test_status_counts(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="1", status=TaskStatus.TODO))
        repository.insert(_make_task(task_id="2", status=TaskStatus.DOING))
        repository.insert(_make_task(task_id="3", status=TaskStatus.DOING))
        repository.insert(_make_task(task_id="4", status=TaskStatus.OVERDUE))
        counts = repository.get_status_counts()
        assert counts[TaskStatus.TODO] == 1
        assert counts[TaskStatus.DOING] == 2
        assert counts[TaskStatus.OVERDUE] == 1

    def test_heatmap_data(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="1", deadline_date=date(2026, 5, 10)))
        repository.insert(_make_task(task_id="2", deadline_date=date(2026, 5, 10)))
        repository.insert(_make_task(task_id="3", deadline_date=date(2026, 5, 15)))
        data = repository.get_heatmap_data(2026)
        assert data[date(2026, 5, 10)] == 2
        assert data[date(2026, 5, 15)] == 1


class TestEmptyState:
    """Verify welcome/empty-state scenarios — "今日无事，找点事情干一下吧"."""

    def test_overdue_filter_empty_when_all_future(self, repository: TaskRepository) -> None:
        """All tasks have future deadlines → overdue filter returns empty."""
        future = date.today().replace(year=date.today().year + 1)
        repository.insert(_make_task(task_id="1", deadline_date=future))
        repository.insert(_make_task(task_id="2", deadline_date=future))
        results = repository.search(TaskFilter(overdue_only=True))
        assert len(results) == 0

    def test_today_filter_empty_when_no_tasks_today(self, repository: TaskRepository) -> None:
        """Tasks are all in the distant future → today filter returns empty."""
        far = date.today().replace(year=date.today().year + 1)
        repository.insert(_make_task(task_id="1", deadline_date=far, scheduled_date=far))
        today = date.today()
        results = repository.search(TaskFilter(date_from=today, date_to=today))
        assert len(results) == 0

    def test_empty_database(self, repository: TaskRepository) -> None:
        """No tasks at all → any filter returns empty."""
        results = repository.search(TaskFilter())
        assert len(results) == 0


class TestOverdueStatus:
    """Auto OVERDUE detection and reversion via refresh_overdue_status()."""

    def test_auto_overdue(self, repository: TaskRepository) -> None:
        """Tasks past deadline become OVERDUE; future/DONE tasks don't."""
        from datetime import date as _date
        from datetime import timedelta
        past = _date.today() - timedelta(days=7)
        future = _date.today() + timedelta(days=365)
        repository.insert(_make_task(task_id="1", title="past", deadline_date=past))
        repository.insert(_make_task(task_id="2", title="future", deadline_date=future))
        repository.insert(_make_task(task_id="3", title="done", status=TaskStatus.DONE, deadline_date=past))

        changed = repository.refresh_overdue_status()
        changed_ids = [t.id for t, _ in changed]
        assert "1" in changed_ids
        assert "2" not in changed_ids
        assert "3" not in changed_ids

        t1 = repository.get_by_id("1")
        assert t1 is not None
        assert t1.status == TaskStatus.OVERDUE

    def test_revert_overdue(self, repository: TaskRepository) -> None:
        """OVERDUE tasks with future deadline revert to DOING."""
        from datetime import date as _date
        from datetime import timedelta
        future = _date.today() + timedelta(days=365)
        task = _make_task(task_id="1", title="revert", status=TaskStatus.OVERDUE, deadline_date=future)
        repository.insert(task)

        changed = repository.refresh_overdue_status()
        assert "1" in [t.id for t, _ in changed]

        t1 = repository.get_by_id("1")
        assert t1 is not None
        assert t1.status == TaskStatus.DOING

    def test_sort_order_includes_overdue(self, repository: TaskRepository) -> None:
        """OVERDUE sorts before DOING."""
        today = date.today()
        repository.insert(_make_task(task_id="1", status=TaskStatus.DOING, deadline_date=today))
        repository.insert(_make_task(task_id="2", status=TaskStatus.OVERDUE, deadline_date=today))
        results = repository.search(
            TaskFilter(sort_by=[SortCriterion("status", ascending=True)])
        )
        statuses = [r.status for r in results]
        assert statuses.index(TaskStatus.OVERDUE) < statuses.index(TaskStatus.DOING)


class TestUrgencySort:
    """Sort by explicit urgency → deadline_date ASC → created_at ASC."""

    def test_urgency_sort_explicit_levels(self, repository: TaskRepository) -> None:
        """紧急(0) before 重要(1) before 关注(2) before 普通(3)."""
        today = date.today()
        repository.insert(_make_task(task_id="urgent", deadline_date=today, urgency=0))
        repository.insert(_make_task(task_id="high", deadline_date=today, urgency=1))
        repository.insert(_make_task(task_id="medium", deadline_date=today, urgency=2))
        repository.insert(_make_task(task_id="normal", deadline_date=today, urgency=3))

        results = repository.search(
            TaskFilter(sort_by=[SortCriterion("urgency", ascending=True)], show_archived=True)
        )
        ids = [r.id for r in results]
        assert ids.index("urgent") < ids.index("high") < ids.index("medium") < ids.index("normal")

    def test_urgency_sort_same_level_by_deadline(self, repository: TaskRepository) -> None:
        """Same urgency → earlier deadline first."""
        from datetime import timedelta
        today = date.today()
        repository.insert(_make_task(task_id="far", deadline_date=today + timedelta(days=30), urgency=3))
        repository.insert(_make_task(task_id="near", deadline_date=today + timedelta(days=1), urgency=3))
        repository.insert(_make_task(task_id="overdue", deadline_date=today - timedelta(days=5), urgency=3))

        results = repository.search(
            TaskFilter(sort_by=[SortCriterion("urgency", ascending=True)], show_archived=True)
        )
        ids = [r.id for r in results]
        assert ids.index("overdue") < ids.index("near") < ids.index("far")

    def test_urgency_sort_null_deadline_last(self, repository: TaskRepository) -> None:
        """NULL deadline sorts after explicit deadlines within same urgency."""
        today = date.today()
        repository.insert(_make_task(task_id="no_dl", deadline_date=None, urgency=3))
        repository.insert(_make_task(task_id="has_dl", deadline_date=today, urgency=3))

        results = repository.search(
            TaskFilter(sort_by=[SortCriterion("urgency", ascending=True)], show_archived=True)
        )
        ids = [r.id for r in results]
        assert ids.index("has_dl") < ids.index("no_dl")

    def test_urgency_sort_same_all_by_created(self, repository: TaskRepository) -> None:
        """Same urgency + deadline → earlier created_at first."""
        today = date.today()
        t1 = _make_task(task_id="first", deadline_date=today, urgency=3)
        t2 = _make_task(task_id="second", deadline_date=today, urgency=3)
        repository.insert(t1)
        repository.insert(t2)

        results = repository.search(
            TaskFilter(sort_by=[SortCriterion("urgency", ascending=True)], show_archived=True)
        )
        ids = [r.id for r in results]
        assert ids.index("first") < ids.index("second")


# ---------------------------------------------------------------------------
# 批操作回归 —— set-based SQL（单事务 executemany）改写后的行为锁定
# ---------------------------------------------------------------------------


class TestBatchOperationsRegression:
    """断言返回值、字段落库、activity_log 文案、raw_md 与 FTS5 可检索。"""

    @staticmethod
    def _formatter():
        from src.services.md_formatter import MarkdownTaskFormatter

        return MarkdownTaskFormatter()

    @staticmethod
    def _fts_ids(repository: TaskRepository, term: str) -> list[str]:
        rows = repository.conn.execute(
            "SELECT id FROM tasks WHERE rowid IN "
            "(SELECT rowid FROM tasks_fts WHERE tasks_fts MATCH ?)",
            (term,),
        ).fetchall()
        return [r[0] for r in rows]

    def test_batch_update_status_fields_and_fts(self, repository: TaskRepository) -> None:
        fmt = self._formatter()
        ids = []
        for i in range(3):
            repository.insert(_make_task(task_id=f"s{i}", title=f"alpha{i}"))
            ids.append(f"s{i}")

        assert repository.batch_update_status(ids, TaskStatus.DOING, formatter=fmt) == 3

        for i, tid in enumerate(ids):
            t = repository.get_by_id(tid)
            assert t is not None
            assert t.status == TaskStatus.DOING
            assert t.raw_md == fmt.format(t)
            assert t.raw_md.startswith("- [   ] alpha")
            assert len(t.activity_log) == 1
            entry = t.activity_log[0]
            assert entry["content"] == "[批量操作] 状态变更: 待办 -> 进行中"
            assert entry["status"] == "DOING"
            assert entry["progress"] == 0
            assert self._fts_ids(repository, f"alpha{i}") == [tid]

    def test_batch_update_status_done_sets_progress_and_completed_at(
        self, repository: TaskRepository
    ) -> None:
        repository.insert(
            _make_task(task_id="d1", title="收尾项", deadline_date=date(2026, 3, 1))
        )
        assert repository.batch_update_status(["d1"], TaskStatus.DONE) == 1

        got = repository.get_by_id("d1")
        assert got.status == TaskStatus.DONE
        assert got.progress == 100
        assert got.completed_at == datetime(2026, 3, 1)
        assert got.activity_log[-1]["content"] == "[批量操作] 状态变更: 待办 -> 已完成"
        assert got.activity_log[-1]["progress"] == 100

    def test_batch_update_status_empty_and_missing(self, repository: TaskRepository) -> None:
        assert repository.batch_update_status([], TaskStatus.DOING) == 0
        assert repository.batch_update_status(["nope"], TaskStatus.DOING) == 0

    def test_batch_update_urgency_fields_raw_md_and_fts(
        self, repository: TaskRepository
    ) -> None:
        fmt = self._formatter()
        repository.insert(_make_task(task_id="u1", title="beta1"))

        assert repository.batch_update_urgency(["u1"], 0, formatter=fmt) == 1
        got = repository.get_by_id("u1")
        assert got.urgency == 0
        assert got.raw_md == fmt.format(got)
        assert "***" in got.raw_md
        assert got.activity_log == []
        assert self._fts_ids(repository, "beta1") == ["u1"]

        assert repository.batch_update_urgency(["u1"], 2) == 1
        assert repository.get_by_id("u1").urgency == 2
        assert repository.batch_update_urgency(["nope"], 1) == 0

    def test_batch_delete_removes_rows_and_fts(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="x1", title="gamma1"))
        repository.insert(_make_task(task_id="x2", title="gamma2"))

        assert repository.batch_delete(["x1", "x2"]) == 2
        assert repository.get_by_id("x1") is None
        assert repository.get_by_id("x2") is None
        assert self._fts_ids(repository, "gamma1") == []
        assert repository.batch_delete([]) == 0
        assert repository.batch_delete(["x1"]) == 0

    def test_batch_suspend_and_restart(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="k1", title="可中止"))

        assert repository.batch_suspend(["k1"]) == 1
        got = repository.get_by_id("k1")
        assert got.suspended is True
        assert len(got.activity_log) == 1
        assert got.activity_log[-1]["content"] == "[批量操作] 任务已中止"
        assert got.activity_log[-1]["status"] == "TODO"

        assert repository.batch_restart(["k1"]) == 1
        got = repository.get_by_id("k1")
        assert got.suspended is False
        assert len(got.activity_log) == 2
        assert got.activity_log[-1]["content"] == "[批量操作] 任务已恢复"

        assert repository.batch_suspend(["missing"]) == 0

    def test_batch_postpone_fields_raw_md_and_fts(self, repository: TaskRepository) -> None:
        fmt = self._formatter()
        base = date.today() + timedelta(days=10)
        repository.insert(_make_task(task_id="z1", title="epsilon", deadline_date=base))
        repository.insert(_make_task(task_id="z2", title="zeta"))

        assert repository.batch_postpone(["z1", "z2"], 3, formatter=fmt) == 2

        got1 = repository.get_by_id("z1")
        assert got1.deadline_date == base + timedelta(days=3)
        assert got1.raw_md == fmt.format(got1)
        assert got1.activity_log[-1]["content"] == (
            f"[批量操作] 延后处理: 截止时间 {base.isoformat()} -> "
            f"{(base + timedelta(days=3)).isoformat()}（+3天）"
        )
        assert self._fts_ids(repository, "epsilon") == ["z1"]

        got2 = repository.get_by_id("z2")
        assert got2.deadline_date == date.today() + timedelta(days=3)
        assert got2.activity_log[-1]["content"].startswith(
            "[批量操作] 延后处理: 截止时间 无 -> "
        )

    def test_archive_batch_sets_archived_and_timestamp(
        self, repository: TaskRepository
    ) -> None:
        repository.insert(_make_task(task_id="a1", title="待归档", status=TaskStatus.DONE))

        assert repository.archive_batch(["a1"]) == 1
        got = repository.get_by_id("a1")
        assert got.archived is True
        assert got.archived_at is not None
        assert repository.archive_batch([]) == 0
        assert repository.archive_batch(["nope"]) == 0

    def test_refresh_overdue_status_batched(self, repository: TaskRepository) -> None:
        fmt = self._formatter()
        past = date.today() - timedelta(days=5)
        future = date.today() + timedelta(days=60)
        repository.insert(_make_task(task_id="o1", title="overdue1", deadline_date=past))
        repository.insert(
            _make_task(
                task_id="o2", title="revert1", status=TaskStatus.OVERDUE,
                deadline_date=future,
            )
        )
        repository.insert(
            _make_task(
                task_id="o3", title="done1", status=TaskStatus.DONE, deadline_date=past,
            )
        )

        changed = repository.refresh_overdue_status(formatter=fmt)
        old_by_id = {t.id: old for t, old in changed}
        assert old_by_id == {"o1": TaskStatus.TODO, "o2": TaskStatus.OVERDUE}

        assert repository.get_by_id("o1").status == TaskStatus.OVERDUE
        assert repository.get_by_id("o2").status == TaskStatus.DOING
        assert repository.get_by_id("o3").status == TaskStatus.DONE
        assert repository.conn.execute("PRAGMA user_version").fetchone()[0] == 8

    def test_recalc_all_activity_counts_batched(self, repository: TaskRepository) -> None:
        repository.insert(_make_task(task_id="r1", title="recalc"))
        task = repository.get_by_id("r1")
        task.activity_log = [{"ts": datetime.now().isoformat(), "content": "手工"}]
        repository.update(task)

        assert repository.recalc_all_activity_counts() == 1
        assert repository.get_by_id("r1").activity_today == 1
        assert repository.conn.execute("PRAGMA user_version").fetchone()[0] == 8
