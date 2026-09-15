"""TimelineModel — 时间轴（甘特）数据内核。

纯 Python / 不依赖 Qt Widgets，便于单元测试；``TimelineTableView`` 只需读取
``TimelineData`` 即可绘制，布局数学全部集中在此。

时间轴粒度与预设（对应速览栏 / 总览页）：

===========  ==========================================================
``today``    今天
``yesterday``昨天
``week``     本周（周一 → 周日）
``last_week``上周（周一 → 周日）
``month``    本月（1 日 → 月末）
``last_month``上月（1 日 → 月末）
``30d``      近 30 天（今天往前 29 天 → 今天）
===========  ==========================================================

每行的时间区间：``start = scheduled_date or created_at.date() or deadline_date``，
``end = deadline_date or start``；若两端都缺失则用 ``today``。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from ...models.task import Task
from ...models.task_status import TaskStatus

#: 支持的粒度键
RANGE_KEYS = ("today", "yesterday", "week", "last_week", "month", "last_month", "30d")


@dataclass(frozen=True)
class TimelineRow:
    """时间轴中的一行（一个任务）。"""

    task_id: str
    title: str
    status: str  # TaskStatus.value
    tags: tuple[str, ...]
    urgency: int
    progress: int
    start: date  # 原始区间起点
    end: date  # 原始区间终点（含）
    offset_days: int  # start 相对轴起点的偏移（可为负 → 需左裁剪）
    span_days: int  # end - start + 1（>= 1）
    overdue: bool

    @property
    def clipped_offset(self) -> int:
        """在轴范围内绘制时的起点偏移（>= 0）。"""
        return max(0, self.offset_days)

    def clipped_span(self, axis_len: int) -> int:
        """在轴范围内绘制时的跨度（>= 1，且不超出轴长）。"""
        start = self.clipped_offset
        if start >= axis_len:
            return 0
        return max(1, min(self.span_days - (start - self.offset_days), axis_len - start))


@dataclass(frozen=True)
class TimelineData:
    """一次构建的完整时间轴数据。"""

    range_key: str
    axis_start: date
    axis_end: date
    days: tuple[date, ...]
    rows: tuple[TimelineRow, ...]
    today_index: int | None  # 今天在 days 中的下标（不在范围内为 None）

    @property
    def axis_len(self) -> int:
        return len(self.days)

    @property
    def row_count(self) -> int:
        return len(self.rows)


def resolve_range(range_key: str, today: date) -> tuple[date, date]:
    """把粒度键解析成 ``(axis_start, axis_end)``（均含端点）。"""
    if range_key == "today":
        return today, today
    if range_key == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if range_key == "week":
        monday = today - timedelta(days=today.isoweekday() - 1)
        return monday, monday + timedelta(days=6)
    if range_key == "last_week":
        monday = today - timedelta(days=today.isoweekday() + 6)
        return monday, monday + timedelta(days=6)
    if range_key == "month":
        first = today.replace(day=1)
        last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return first, last
    if range_key == "last_month":
        last_day = today.replace(day=1) - timedelta(days=1)
        first = last_day.replace(day=1)
        return first, last_day
    if range_key == "30d":
        return today - timedelta(days=29), today
    raise ValueError(f"未知时间轴粒度: {range_key!r}")


def _task_interval(task: Task, today: date) -> tuple[date, date]:
    """任务的原始时间区间（含端点）。"""
    created = task.created_at.date() if task.created_at else None
    start = task.scheduled_date or created or task.deadline_date or today
    end = task.deadline_date or start
    if end < start:  # 截止早于计划 → 以起点为准，避免负跨度
        end = start
    return start, end


class TimelineModel:
    """把任务列表构建成时间轴行（可排序、可按粒度裁剪）。"""

    #: 支持的排序键 → 显示名
    SORTS = {
        "deadline": "截止优先",
        "urgency": "优先级优先",
        "start": "计划起点",
    }

    def build(
        self,
        tasks: list[Task],
        range_key: str = "week",
        today: date | None = None,
        *,
        statuses: set[TaskStatus] | None = None,
        search_text: str = "",
        urgencies: set[int] | None = None,
        sort_key: str = "deadline",
        include_archived: bool = False,
    ) -> TimelineData:
        """构建时间轴数据。

        Args:
            tasks: 候选任务。
            range_key: 粒度键（见 :data:`RANGE_KEYS`）。
            today: 基准日，默认 ``date.today()``。
            statuses: 仅保留这些状态（``None`` = 全部）。
            search_text: 标题 / 标签的模糊匹配（大小写不敏感）。
            urgencies: 仅保留这些优先级（``None`` = 全部）。
            sort_key: :data:`SORTS` 中的排序键。
            include_archived: 是否包含已归档任务。
        """
        today = today or date.today()
        axis_start, axis_end = resolve_range(range_key, today)
        days = tuple(
            axis_start + timedelta(days=i)
            for i in range((axis_end - axis_start).days + 1)
        )

        wanted = search_text.strip().casefold()
        rows: list[TimelineRow] = []
        for task in tasks:
            if not include_archived and task.archived:
                continue
            if statuses is not None and task.status not in statuses:
                continue
            if urgencies is not None and getattr(task, "urgency", 3) not in urgencies:
                continue
            if wanted:
                haystack = f"{task.title} {' '.join(task.tags or [])}".casefold()
                if wanted not in haystack:
                    continue

            start, end = _task_interval(task, today)
            if end < axis_start or start > axis_end:  # 与轴无交集
                continue

            rows.append(
                TimelineRow(
                    task_id=task.id,
                    title=task.title,
                    status=task.status.value,
                    tags=tuple(task.tags or []),
                    urgency=getattr(task, "urgency", 3),
                    progress=task.progress,
                    start=start,
                    end=end,
                    offset_days=(start - axis_start).days,
                    span_days=(end - start).days + 1,
                    overdue=task.status == TaskStatus.OVERDUE,
                )
            )

        rows.sort(
            key=lambda r: (
                r.end,  # 截止优先
                r.urgency,
                r.start,
                r.title,
            )
        )
        if sort_key == "urgency":
            rows.sort(key=lambda r: (r.urgency, r.end, r.title))
        elif sort_key == "start":
            rows.sort(key=lambda r: (r.start, r.title))

        today_index = days.index(today) if axis_start <= today <= axis_end else None
        return TimelineData(
            range_key=range_key,
            axis_start=axis_start,
            axis_end=axis_end,
            days=days,
            rows=tuple(rows),
            today_index=today_index,
        )
