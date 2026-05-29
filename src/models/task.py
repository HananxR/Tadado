"""Task dataclass — the core domain model."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from .task_status import TaskStatus


@dataclass
class Task:
    """A single task defined by a Markdown line."""

    id: str
    raw_md: str
    title: str
    status: TaskStatus = TaskStatus.TODO
    tags: list[str] = field(default_factory=list)
    scheduled_date: Optional[date] = None
    deadline_date: Optional[date] = None
    deadline_time: Optional[str] = None
    partition_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    archived: bool = False
    archived_at: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    parent_id: Optional[str] = None
    notes: Optional[str] = None
    activity_log: list[dict] = field(default_factory=list)
    progress: int = 0
    suspended: bool = False

    @property
    def is_overdue(self) -> bool:
        """True when the deadline has passed and the task is still active."""
        if self.deadline_date is None:
            return False
        if self.status in (TaskStatus.DONE, TaskStatus.OVERDUE):
            return False
        return self.deadline_date < date.today()

    @property
    def is_due_soon(self, days: int = 2) -> bool:
        """True when the deadline is within the next *days* days."""
        if self.deadline_date is None:
            return False
        if self.status in (TaskStatus.DONE, TaskStatus.OVERDUE):
            return False
        today = date.today()
        delta = (self.deadline_date - today).days
        return 0 <= delta <= days

    @property
    def urgency_score(self) -> float:
        """Urgency for sorting/coloring: positive=overdue days, negative=days until due.

        DONE tasks (-9999) and tasks without deadline (-9998) are least urgent.
        """
        if self.status == TaskStatus.DONE:
            return -9999.0
        if self.deadline_date is None:
            return -9998.0
        return (date.today() - self.deadline_date).days
