"""Tests for MarkdownTaskFormatter."""

from __future__ import annotations

from datetime import date, datetime

import pytest

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
            scheduled_date=date(2026, 5, 10),
            deadline_date=date(2026, 5, 20),
            tags=["backend"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [   ] <2026-05-10> <2026-05-20> 重构认证模块 #backend"

    def test_minimal_task(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="2",
            raw_md="",
            title="买菜",
            status=TaskStatus.TODO,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [   ] 买菜"

    def test_done_task(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="3",
            raw_md="",
            title="修bug",
            status=TaskStatus.DONE,
            tags=["urgent"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [   ] 修bug #urgent"

    def test_no_tags(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="4",
            raw_md="",
            title="写周报",
            status=TaskStatus.DOING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [   ] 写周报"


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
            scheduled_date=date(2026, 6, 1),
            deadline_date=date(2026, 6, 15),
            tags=["qa", "automation"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        md_line = formatter.format(task)
        parsed = parser.parse(md_line)
        # Status is not in Markdown — parsed back defaults to TODO
        assert parsed.scheduled_date == task.scheduled_date
        assert parsed.deadline_date == task.deadline_date
        assert parsed.title == task.title
        assert parsed.tags == task.tags


class TestOverdueFormat:
    """OVERDUE status formatting."""

    def test_overdue_task(self, formatter: MarkdownTaskFormatter) -> None:
        task = Task(
            id="o1",
            raw_md="",
            title="已逾期报告",
            status=TaskStatus.OVERDUE,
            deadline_date=date(2026, 5, 1),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        result = formatter.format(task)
        assert result == "- [   ] <2026-05-01> 已逾期报告"

    def test_overdue_round_trip(self, formatter: MarkdownTaskFormatter) -> None:
        from src.services.md_parser import MarkdownTaskParser

        parser = MarkdownTaskParser()
        task = Task(
            id="o2",
            raw_md="",
            title="过期任务",
            status=TaskStatus.OVERDUE,
            scheduled_date=date(2026, 4, 1),
            deadline_date=date(2026, 4, 15),
            tags=["逾期"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        md_line = formatter.format(task)
        parsed = parser.parse(md_line)
        # Status is not in Markdown — parsed back defaults to TODO
        assert parsed.scheduled_date == date(2026, 4, 1)
        assert parsed.deadline_date == date(2026, 4, 15)


class TestLinksRoundTrip:
    """含 [[链接]] 的往返稳定性锁定（阶段 6）。"""

    def test_round_trip_with_links(self, formatter: MarkdownTaskFormatter) -> None:
        from src.services.md_parser import MarkdownTaskParser

        parser = MarkdownTaskParser()
        raw = "- [   ] 重构 [[认证模块]] #后端"
        parsed = parser.parse(raw)
        assert parsed.title == "重构 [[认证模块]]"
        assert parsed.links == ["认证模块"]

        md = formatter.format(parsed)
        assert "[[认证模块]]" in md  # 链接字面量完整保留
        assert md == raw

        reparsed = parser.parse(md)
        assert reparsed.title == parsed.title
        assert reparsed.links == parsed.links
        assert formatter.format(reparsed) == md  # 二次往返稳定

    def test_round_trip_with_links_and_dates(
        self, formatter: MarkdownTaskFormatter
    ) -> None:
        from src.services.md_parser import MarkdownTaskParser

        parser = MarkdownTaskParser()
        raw = "- [   ] <2026-05-10> <2026-05-20> 重构 [[认证模块]] #后端"
        parsed = parser.parse(raw)

        md = formatter.format(parsed)
        assert md == raw
        assert "[[认证模块]]" in md
        assert parser.parse(md).links == ["认证模块"]
