"""Markdown task formatter — converts structured Task fields back to a canonical Markdown line."""

from __future__ import annotations

from ..models.task import Task
from ..models.task_status import TaskStatus


class MarkdownTaskFormatter:
    """Produces a canonical Markdown line from a :class:`Task` (or its fields)."""

    def format(self, task: Task) -> str:
        """Format a Task into its canonical Markdown line.

        Guarantees stable output: same fields always produce the same string.
        """
        return self.format_fields(
            status=task.status,
            scheduled_date=task.scheduled_date,
            deadline_date=task.deadline_date,
            deadline_time=task.deadline_time,
            title=task.title,
            tags=task.tags,
            urgency=task.urgency,
        )

    @staticmethod
    def format_fields(
        status: TaskStatus = TaskStatus.TODO,
        scheduled_date: str | None = None,
        deadline_date: str | None = None,
        deadline_time: str | None = None,
        title: str = "",
        tags: list[str] | None = None,
        urgency: int = 3,
    ) -> str:
        """Low-level formatting from individual fields.

        Args:
            status: Task status keyword.
            scheduled_date: Scheduled date as YYYY-MM-DD string (or None).
            deadline_date: Deadline date as YYYY-MM-DD string (or None).
            deadline_time: Deadline time as HH:MM string (or None).
            title: Clean task description (without tags).
            tags: Tag strings without the '#' prefix.
            urgency: Priority level (0=紧急, 1=重要, 2=关注, 3=普通).
        """
        parts: list[str] = []

        # Priority bracket: [***]=urgent, [** ]=high, [*  ]=medium, [   ]=normal
        stars = '*' * (3 - urgency) if urgency < 3 else '   '
        parts.append(f"- [{stars:<3}]")

        # Status keyword
        parts.append(status.value)

        # Scheduled date
        if scheduled_date:
            parts.append(f"<{scheduled_date}>")

        # Deadline date (with optional time)
        if deadline_date:
            if deadline_time:
                parts.append(f"<{deadline_date} {deadline_time}>")
            else:
                parts.append(f"<{deadline_date}>")

        # Title
        parts.append(title)

        # Tags
        if tags:
            tag_str = " ".join(f"#{t}" for t in tags)
            parts.append(tag_str)

        return " ".join(parts)
