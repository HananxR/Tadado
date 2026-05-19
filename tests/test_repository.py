"""Tests for TaskRepository."""

from __future__ import annotations

import uuid
from datetime import date, datetime

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
        created_at=now,
        updated_at=now,
        archived=archived,
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
        counts = repository.get_status_counts()
        assert counts[TaskStatus.TODO] == 1
        assert counts[TaskStatus.DOING] == 2

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
