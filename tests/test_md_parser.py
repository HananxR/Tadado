"""Tests for MarkdownTaskParser."""

from __future__ import annotations

from datetime import date

import pytest

from src.models.task_status import TaskStatus
from src.services.md_parser import MarkdownTaskParser


@pytest.fixture
def parser() -> MarkdownTaskParser:
    return MarkdownTaskParser()


class TestParseStandard:
    """Full-format task lines."""

    def test_full_format(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] TODO <2026-05-10> <2026-05-20> 重构认证模块 #backend")
        assert result.status == TaskStatus.TODO
        assert result.scheduled_date == date(2026, 5, 10)
        assert result.deadline_date == date(2026, 5, 20)
        assert result.title == "重构认证模块"
        assert "backend" in result.tags

    def test_minimal_format(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] TODO 买菜")
        assert result.status == TaskStatus.TODO
        assert result.scheduled_date is None
        assert result.deadline_date is None
        assert result.title == "买菜"
        assert result.tags == []

    def test_done_with_checkbox(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [x] DONE 修复bug #urgent")
        assert result.checkbox_checked is True
        assert result.status == TaskStatus.DONE
        assert result.title == "修复bug"
        assert "urgent" in result.tags

    def test_all_status_keywords(self, parser: MarkdownTaskParser) -> None:
        for status in TaskStatus:
            line = f"- [ ] {status.value} 测试任务"
            result = parser.parse(line)
            assert result.status == status

    def test_multiple_tags(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] DOING 编写API文档 #docs #backend #urgent")
        assert result.tags == ["docs", "backend", "urgent"]

    def test_scheduled_only(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] TODO <2026-12-25> 圣诞节准备")
        assert result.scheduled_date == date(2026, 12, 25)
        assert result.deadline_date is None


class TestParseFallback:
    """Lines that don't match the strict pattern."""

    def test_missing_checkbox(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("TODO 处理发票")
        assert result.status == TaskStatus.TODO
        assert result.title == "处理发票"

    def test_missing_keyword(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] 随便写点什么")
        assert result.status == TaskStatus.TODO  # default
        assert result.title == "随便写点什么"

    def test_plain_text(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("整理桌面")
        assert result.status == TaskStatus.TODO
        assert result.title == "整理桌面"

    def test_legacy_urgent_fallback(self, parser: MarkdownTaskParser) -> None:
        """URGENT keyword no longer exists — treated as plain text, defaults to TODO."""
        result = parser.parse("URGENT 服务器宕机 #critical")
        assert result.status == TaskStatus.TODO
        assert "critical" in result.tags

    def test_case_insensitive(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] todo 随便")
        assert result.status == TaskStatus.TODO


class TestErrorHandling:
    def test_empty_string(self, parser: MarkdownTaskParser) -> None:
        with pytest.raises(ValueError, match="Empty"):
            parser.parse("")

    def test_whitespace_only(self, parser: MarkdownTaskParser) -> None:
        with pytest.raises(ValueError, match="Empty"):
            parser.parse("   ")

    def test_invalid_date_graceful(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] TODO <not-a-date> 测试")
        assert result.scheduled_date is None
        assert result.deadline_date is None


class TestParseBatch:
    def test_mixed_valid_invalid(self, parser: MarkdownTaskParser) -> None:
        text = """- [ ] TODO 任务1
这不是任务
- [x] DONE 任务2 #done

- [ ] DOING 任务3"""
        results = parser.parse_batch(text)
        parsed = [r[0] for r in results if r[0] is not None]
        errors = [r for r in results if r[0] is None]
        assert len(parsed) == 4
        assert len(errors) == 0  # fallback makes everything parse


class TestDeadlineTime:
    """Tests for optional deadline time in <YYYY-MM-DD HH:MM> format."""

    def test_deadline_with_time(self, parser: MarkdownTaskParser) -> None:
        parsed = parser.parse(
            "- [ ] TODO <2026-05-10> <2026-05-20 14:30> 任务 #tag"
        )
        assert parsed.deadline_date == date(2026, 5, 20)
        assert parsed.deadline_time == "14:30"
        assert parsed.scheduled_date == date(2026, 5, 10)

    def test_deadline_without_time(self, parser: MarkdownTaskParser) -> None:
        # Single date → scheduled_date; two dates → second is deadline
        parsed = parser.parse(
            "- [ ] TODO <2026-05-10> <2026-06-01> 任务"
        )
        assert parsed.scheduled_date == date(2026, 5, 10)
        assert parsed.deadline_date == date(2026, 6, 1)
        assert parsed.deadline_time is None

    def test_deadline_time_fallback(self, parser: MarkdownTaskParser) -> None:
        parsed = parser._fallback_parse(
            "TODO <2026-05-10> <2026-06-15 09:00> 任务描述"
        )
        assert parsed.deadline_date == date(2026, 6, 15)
        assert parsed.deadline_time == "09:00"

    def test_deadline_time_t_separator(self, parser: MarkdownTaskParser) -> None:
        parsed = parser.parse(
            "- [ ] DOING <2026-07-01T18:00> 任务"
        )
        assert parsed.deadline_date == date(2026, 7, 1)
        assert parsed.deadline_time == "18:00"


class TestOverdue:
    """OVERDUE status parsing."""

    def test_overdue_parsing(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] OVERDUE <2026-05-01> 已逾期任务 #urgent")
        assert result.status == TaskStatus.OVERDUE
        assert result.scheduled_date == date(2026, 5, 1)
        assert result.title == "已逾期任务"

    def test_overdue_fallback(self, parser: MarkdownTaskParser) -> None:
        result = parser.parse("- [ ] OVERDUE 简洁逾期")
        assert result.status == TaskStatus.OVERDUE

    def test_old_status_fallback_to_todo(self, parser: MarkdownTaskParser) -> None:
        """WAIT/LATER keywords now map to TODO via from_string fallback."""
        result = parser.parse("- [ ] WAIT 等待中")
        assert result.status == TaskStatus.TODO

        result = parser.parse("- [ ] LATER 稍后做")
        assert result.status == TaskStatus.TODO
