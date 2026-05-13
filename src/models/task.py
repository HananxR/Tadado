"""Task dataclass — the core domain model."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from .priority import Priority
from .task_status import TaskStatus


@dataclass
class Task:
    """A single task defined by a Markdown line."""

    id: str
    raw_md: str
    title: str
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.NONE
    tags: list[str] = field(default_factory=list)
    scheduled_date: Optional[date] = None
    deadline_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    archived: bool = False
    archived_at: Optional[datetime] = None
    recurrence_rule: Optional[str] = None
    parent_id: Optional[str] = None
    notes: Optional[str] = None
    activity_log: list[dict] = field(default_factory=list)

    @property
    def is_overdue(self) -> bool:
        """True when the deadline has passed and the task is still active."""
        if self.deadline_date is None:
            return False
        if self.status in (TaskStatus.DONE,):
            return False
        return self.deadline_date < date.today()

    @property
    def is_due_soon(self, days: int = 2) -> bool:
        """True when the deadline is within the next *days* days."""
        if self.deadline_date is None:
            return False
        if self.status in (TaskStatus.DONE,):
            return False
        today = date.today()
        delta = (self.deadline_date - today).days
        return 0 <= delta <= days
