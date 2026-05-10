"""Filter and sort criteria for task queries."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .priority import Priority
from .task_status import TaskStatus


@dataclass
class SortCriterion:
    """A single sort dimension for task list ordering."""

    field: str  # "deadline" | "priority" | "created" | "status" | "title" | "scheduled"
    ascending: bool = True


@dataclass
class TaskFilter:
    """Filter parameters for querying the task list."""

    search_text: str = ""
    statuses: Optional[set[TaskStatus]] = None  # None means all
    priorities: Optional[set[Priority]] = None
    min_priority: Optional[Priority] = None
    tags: Optional[set[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    overdue_only: bool = False
    show_archived: bool = False
    sort_by: list[SortCriterion] = field(
        default_factory=lambda: [SortCriterion("deadline", ascending=True)]
    )
    limit: Optional[int] = None
    offset: int = 0
