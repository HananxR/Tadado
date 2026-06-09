"""Filter and sort criteria for task queries."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .task_status import TaskStatus


@dataclass
class SortCriterion:
    """A single sort dimension for task list ordering."""

    field: str  # "deadline" | "created" | "status" | "title" | "scheduled" | "urgency"
    ascending: bool = True


@dataclass
class TaskFilter:
    """Filter parameters for querying the task list."""

    search_text: str = ""
    statuses: Optional[set[TaskStatus]] = None  # None means all
    tags: Optional[set[str]] = None
    partition_id: Optional[str] = None  # None means all partitions
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    created_from: Optional[date] = None
    created_to: Optional[date] = None
    progress_min: int = 0
    progress_max: int = 100
    activity_field: Optional[str] = None  # "activity_today" / "activity_week" 等
    activity_min: int = 0  # activity >= N，0=不过滤
    overdue_only: bool = False
    show_archived: bool = False
    show_suspended: bool = True  # always show, use visual dimming instead
    suspended_only: bool = False
    urgencies: Optional[set[int]] = None  # None = all, {0,1,2,3} for specific levels
    sort_by: list[SortCriterion] = field(
        default_factory=lambda: [SortCriterion("deadline", ascending=True)]
    )
    limit: Optional[int] = None
    offset: int = 0
