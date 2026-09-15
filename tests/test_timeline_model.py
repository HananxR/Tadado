"""Tests for TimelineModel — 阶段 3 时间轴（甘特）纯逻辑内核。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.models.task import Task
from src.models.task_status import TaskStatus
from src.ui.timeline import TimelineModel, resolve_range

TODAY = date(2026, 9, 12)  # 周六


def make_task(
    task_id: str,
    title: str = "任务",
    *,
    status: TaskStatus = TaskStatus.TODO,
    tags: list[str] | None = None,
    urgency: int = 3,
    progress: int = 0,
    scheduled_date: date | None = None,
    deadline_date: date | None = None,
    created_at: date | None = None,
    archived: bool = False,
) -> Task:
    return Task(
        id=task_id,
        raw_md=f"- [ ] {title}",
        title=title,
        status=status,
        tags=list(tags or []),
        urgency=urgency,
        progress=progress,
        scheduled_date=scheduled_date,
        deadline_date=deadline_date,
        created_at=datetime.combine(created_at, datetime.min.time()) if created_at else None,
        archived=archived,
    )


# ---------------------------------------------------------------------------
# resolve_range
# ---------------------------------------------------------------------------


class TestResolveRange:
    def test_today(self):
        assert resolve_range("today", TODAY) == (TODAY, TODAY)

    def test_yesterday(self):
        assert resolve_range("yesterday", TODAY) == (
            date(2026, 9, 11), date(2026, 9, 11),
        )

    def test_week_is_monday_to_sunday(self):
        assert resolve_range("week", TODAY) == (date(2026, 9, 7), date(2026, 9, 13))

    def test_last_week(self):
        assert resolve_range("last_week", TODAY) == (
            date(2026, 8, 31), date(2026, 9, 6),
        )

    def test_month(self):
        assert resolve_range("month", TODAY) == (date(2026, 9, 1), date(2026, 9, 30))

    def test_last_month(self):
        assert resolve_range("last_month", TODAY) == (
            date(2026, 8, 1), date(2026, 8, 31),
        )

    def test_30d(self):
        assert resolve_range("30d", TODAY) == (date(2026, 8, 14), TODAY)

    def test_unknown_range_raises(self):
        with pytest.raises(ValueError):
            resolve_range("decade", TODAY)


# ---------------------------------------------------------------------------
# build — 轴与行
# ---------------------------------------------------------------------------


class TestBuildAxis:
    def test_axis_days_and_today_index(self):
        data = TimelineModel().build([], "week", TODAY)
        assert len(data.days) == 7
        assert data.days[0] == date(2026, 9, 7)
        assert data.days[-1] == date(2026, 9, 13)
        assert data.today_index == 5  # 9/12 在 9/7 起第 6 天
        assert data.axis_len == 7
        assert data.row_count == 0

    def test_today_outside_range_gives_none_index(self):
        data = TimelineModel().build([], "last_week", TODAY)
        assert data.today_index is None


class TestBuildRows:
    def test_bar_geometry(self):
        tasks = [
            make_task("a", "跨周任务", scheduled_date=date(2026, 9, 10),
                      deadline_date=date(2026, 9, 14)),
        ]
        data = TimelineModel().build(tasks, "week", TODAY)
        assert data.row_count == 1
        row = data.rows[0]
        assert row.start == date(2026, 9, 10)
        assert row.end == date(2026, 9, 14)
        assert row.offset_days == 3  # 9/10 - 9/7
        assert row.span_days == 5  # 10,11,12,13,14

    def test_left_clipping(self):
        tasks = [
            make_task("a", "越界任务", scheduled_date=date(2026, 9, 1),
                      deadline_date=date(2026, 9, 20)),
        ]
        data = TimelineModel().build(tasks, "week", TODAY)
        row = data.rows[0]
        assert row.offset_days == -6
        assert row.clipped_offset == 0
        assert row.clipped_span(data.axis_len) == 7  # 整轴覆盖

    def test_right_clipping(self):
        tasks = [
            make_task("a", "右越界", scheduled_date=date(2026, 9, 12),
                      deadline_date=date(2026, 9, 30)),
        ]
        data = TimelineModel().build(tasks, "week", TODAY)
        row = data.rows[0]
        assert row.clipped_offset == 5
        assert row.clipped_span(data.axis_len) == 2  # 12,13

    def test_out_of_range_excluded(self):
        tasks = [
            make_task("a", "范围外", created_at=date(2026, 9, 1),
                      scheduled_date=date(2026, 9, 1),
                      deadline_date=date(2026, 9, 1)),
        ]
        assert TimelineModel().build(tasks, "week", TODAY).row_count == 0

    def test_no_dates_falls_back_to_today(self):
        tasks = [make_task("a", "无日期")]
        data = TimelineModel().build(tasks, "week", TODAY)
        assert data.row_count == 1
        assert data.rows[0].start == TODAY
        assert data.rows[0].span_days == 1

    def test_deadline_before_start_is_collapsed(self):
        tasks = [
            make_task("a", "倒挂", scheduled_date=date(2026, 9, 12),
                      deadline_date=date(2026, 9, 10)),
        ]
        row = TimelineModel().build(tasks, "week", TODAY).rows[0]
        assert row.end == row.start
        assert row.span_days == 1

    def test_overdue_flag(self):
        tasks = [
            make_task("a", "逾期", status=TaskStatus.OVERDUE,
                      scheduled_date=date(2026, 9, 8),
                      deadline_date=date(2026, 9, 9)),
            make_task("b", "正常", scheduled_date=date(2026, 9, 8),
                      deadline_date=date(2026, 9, 9)),
        ]
        rows = {r.task_id: r for r in TimelineModel().build(tasks, "week", TODAY).rows}
        assert rows["a"].overdue is True
        assert rows["b"].overdue is False

    def test_metadata_passthrough(self):
        tasks = [
            make_task("a", "元数据", tags=["后端", "紧急"], urgency=1, progress=60,
                      scheduled_date=TODAY, deadline_date=TODAY),
        ]
        row = TimelineModel().build(tasks, "week", TODAY).rows[0]
        assert row.status == "TODO"
        assert row.tags == ("后端", "紧急")
        assert row.urgency == 1
        assert row.progress == 60


# ---------------------------------------------------------------------------
# 过滤
# ---------------------------------------------------------------------------


class TestFilters:
    @staticmethod
    def _tasks() -> list[Task]:
        return [
            make_task("a", "后端重构", tags=["后端"], status=TaskStatus.DOING,
                      scheduled_date=TODAY, deadline_date=TODAY),
            make_task("b", "前端联调", tags=["前端"], status=TaskStatus.DONE,
                      scheduled_date=TODAY, deadline_date=TODAY),
            make_task("c", "归档任务", tags=["旧"], archived=True,
                      scheduled_date=TODAY, deadline_date=TODAY),
        ]

    def test_excludes_archived_by_default(self):
        data = TimelineModel().build(self._tasks(), "week", TODAY)
        assert {r.task_id for r in data.rows} == {"a", "b"}

    def test_include_archived(self):
        data = TimelineModel().build(
            self._tasks(), "week", TODAY, include_archived=True
        )
        assert {r.task_id for r in data.rows} == {"a", "b", "c"}

    def test_status_filter(self):
        data = TimelineModel().build(
            self._tasks(), "week", TODAY, statuses={TaskStatus.DOING}
        )
        assert {r.task_id for r in data.rows} == {"a"}

    def test_search_matches_title_and_tags(self):
        backend = TimelineModel().build(self._tasks(), "week", TODAY, search_text="后端")
        assert {r.task_id for r in backend.rows} == {"a"}
        frontend = TimelineModel().build(self._tasks(), "week", TODAY, search_text="前端")
        assert {r.task_id for r in frontend.rows} == {"b"}

    def test_search_case_insensitive(self):
        tasks = [
            make_task("a", "Refactor Auth", tags=["Backend"],
                      scheduled_date=TODAY, deadline_date=TODAY),
        ]
        data = TimelineModel().build(tasks, "week", TODAY, search_text="backend")
        assert {r.task_id for r in data.rows} == {"a"}


# ---------------------------------------------------------------------------
# 排序
# ---------------------------------------------------------------------------


class TestSorting:
    @staticmethod
    def _tasks() -> list[Task]:
        return [
            make_task("late", "晚", urgency=3,
                      scheduled_date=date(2026, 9, 7), deadline_date=date(2026, 9, 13)),
            make_task("early", "早", urgency=3,
                      scheduled_date=date(2026, 9, 7), deadline_date=date(2026, 9, 8)),
            make_task("urgent", "急", urgency=0,
                      scheduled_date=date(2026, 9, 7), deadline_date=date(2026, 9, 12)),
        ]

    def test_default_deadline_sort(self):
        data = TimelineModel().build(self._tasks(), "week", TODAY, sort_key="deadline")
        assert [r.task_id for r in data.rows] == ["early", "urgent", "late"]

    def test_urgency_sort(self):
        data = TimelineModel().build(self._tasks(), "week", TODAY, sort_key="urgency")
        assert data.rows[0].task_id == "urgent"

    def test_start_sort(self):
        """三者起点相同 → 退化为标题序（确定性）。"""
        data = TimelineModel().build(self._tasks(), "week", TODAY, sort_key="start")
        assert len(data.rows) == 3
        assert [r.title for r in data.rows] == sorted(r.title for r in data.rows)

    def test_start_sort_by_actual_start(self):
        tasks = [
            make_task("later", "晚起步", scheduled_date=date(2026, 9, 10),
                      deadline_date=date(2026, 9, 11)),
            make_task("sooner", "早起步", scheduled_date=date(2026, 9, 8),
                      deadline_date=date(2026, 9, 9)),
        ]
        data = TimelineModel().build(tasks, "week", TODAY, sort_key="start")
        assert [r.task_id for r in data.rows] == ["sooner", "later"]


# ---------------------------------------------------------------------------
# 其他粒度
# ---------------------------------------------------------------------------


class TestOtherRanges:
    def test_30d_includes_earlier_task(self):
        tasks = [
            make_task("a", "较早", scheduled_date=TODAY - timedelta(days=20),
                      deadline_date=TODAY - timedelta(days=19)),
        ]
        assert TimelineModel().build(tasks, "30d", TODAY).row_count == 1
        assert TimelineModel().build(tasks, "week", TODAY).row_count == 0

    def test_month_axis_length(self):
        data = TimelineModel().build([], "month", TODAY)
        assert data.axis_len == 30  # 2026-09
