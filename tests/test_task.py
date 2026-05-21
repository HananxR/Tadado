"""Tests for Task urgency_score."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from src.models.task import Task
from src.models.task_status import TaskStatus


def _make_task(
    status: TaskStatus = TaskStatus.TODO,
    deadline_date: date | None = None,
    progress: int = 0,
) -> Task:
    now = datetime.now()
    return Task(
        id="test",
        raw_md="- [ ] TEST",
        title="测试",
        status=status,
        deadline_date=deadline_date,
        progress=progress,
        created_at=now,
        updated_at=now,
    )


class TestUrgencyScore:
    def test_overdue_positive_score(self) -> None:
        """Past deadline → positive score = overdue days."""
        past = date.today() - timedelta(days=5)
        task = _make_task(status=TaskStatus.DOING, deadline_date=past)
        assert task.urgency_score == 5.0

    def test_today_zero_score(self) -> None:
        """Deadline today → score = 0."""
        task = _make_task(deadline_date=date.today())
        assert task.urgency_score == 0.0

    def test_future_negative_score(self) -> None:
        """Future deadline → negative score = days until due."""
        future = date.today() + timedelta(days=10)
        task = _make_task(deadline_date=future)
        assert task.urgency_score == -10.0

    def test_done_least_urgent(self) -> None:
        """DONE tasks always return -9999 regardless of deadline."""
        past = date.today() - timedelta(days=100)
        task = _make_task(status=TaskStatus.DONE, deadline_date=past)
        assert task.urgency_score == -9999.0

    def test_no_deadline_second_least(self) -> None:
        """Tasks without deadline return -9998."""
        task = _make_task(deadline_date=None)
        assert task.urgency_score == -9998.0

    def test_overdue_status_positive_score(self) -> None:
        """OVERDUE status still computes real score (not excluded)."""
        past = date.today() - timedelta(days=3)
        task = _make_task(status=TaskStatus.OVERDUE, deadline_date=past)
        assert task.urgency_score == 3.0

    def test_done_overrides_deadline(self) -> None:
        """DONE with any deadline → -9999."""
        future = date.today() + timedelta(days=30)
        task = _make_task(status=TaskStatus.DONE, deadline_date=future)
        assert task.urgency_score == -9999.0
