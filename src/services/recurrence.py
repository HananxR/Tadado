"""Recurrence handler — creates new task instances when a recurring task is completed."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from ..models.repository import TaskRepository
from ..models.task import Task
from ..models.task_status import TaskStatus
from ..utils.signal_bus import get_signal_bus

_RECUR_PATTERN = re.compile(r"^\+?(\d+)([dwmy])$")


class TaskRecurrence:
    """Listens for task completion and creates the next instance for recurring tasks."""

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._signal_bus.task_status_changed.connect(self._on_status_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_status_changed(self, task: Task, old_status: TaskStatus) -> None:
        if task.status != TaskStatus.DONE or old_status == TaskStatus.DONE:
            return
        if not task.recurrence_rule:
            return

        offset = self._parse_rule(task.recurrence_rule)
        if offset is None:
            return

        new_scheduled = None
        new_deadline = None
        if task.scheduled_date:
            new_scheduled = task.scheduled_date + offset
        if task.deadline_date:
            new_deadline = task.deadline_date + offset

        new_task = Task(
            id=str(uuid.uuid4()),
            raw_md=task.raw_md,
            title=task.title,
            status=TaskStatus.TODO,
            tags=list(task.tags),
            scheduled_date=new_scheduled,
            deadline_date=new_deadline,
            recurrence_rule=task.recurrence_rule,
            notes=task.notes,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._repository.insert(new_task)
        self._signal_bus.task_created.emit(new_task)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_rule(rule: str) -> timedelta | relativedelta | None:
        """Parse a recurrence rule like +1d, +1w, +1m, +1y."""
        match = _RECUR_PATTERN.match(rule.strip())
        if not match:
            return None
        num = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            return timedelta(days=num)
        if unit == "w":
            return timedelta(weeks=num)
        if unit == "m":
            return relativedelta(months=num)
        if unit == "y":
            return relativedelta(years=num)
        return None
