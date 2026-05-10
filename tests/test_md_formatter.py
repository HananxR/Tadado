"""Tests for MarkdownTaskFormatter."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.models.priority import Priority
from src.models.task import Task
from src.models.task_status import TaskStatus
from src.services.md_formatter import MarkdownTaskFormatter


@pytest.fixture
def formatter() -> MarkdownTaskFormatter:
    return MarkdownTaskFormatter()


class TestFormat:
    def test_full_task(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="1",
            raw_md="",
            title="重构认证模块",
            status=TaskStatus.TODO,
            priority=Priority.A,
            scheduled_date=date(2026, 5, 10),
            deadline_date=date(2026, 5, 20),
            tags=["backend"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [ ] TODO [#A] <2026-05-10> <2026-05-20> 重构认证模块 #backend"

    def test_minimal_task(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="2",
            raw_md="",
            title="买菜",
            status=TaskStatus.TODO,
            priority=Priority.NONE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [ ] TODO 买菜"

    def test_done_task(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="3",
            raw_md="",
            title="修bug",
            status=TaskStatus.DONE,
            priority=Priority.B,
            tags=["urgent"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [x] DONE [#B] 修bug #urgent"

    def test_no_tags(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="4",
            raw_md="",
            title="写周报",
            status=TaskStatus.DOING,
            priority=Priority.NONE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [ ] DOING 写周报"


class TestRoundTrip:
    """Task -> format -> parse should produce equivalent fields."""

    def test_round_trip(self, formatter: MarkdownTaskFormatter) -> None:
        from src.services.md_parser import MarkdownTaskParser

        parser = MarkdownTaskParser()
        task = Task(
            id="r1",
            raw_md="",
            title="编写测试",
            status=TaskStatus.DOING,
            priority=Priority.C,
            scheduled_date=date(2026, 6, 1),
            deadline_date=date(2026, 6, 15),
            tags=["qa", "automation"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        md_line = formatter.format(task)
        parsed = parser.parse(md_line)
        assert parsed.status == task.status
        assert parsed.priority == task.priority
        assert parsed.scheduled_date == task.scheduled_date
        assert parsed.deadline_date == task.deadline_date
        assert parsed.title == task.title
        assert parsed.tags == task.tags
