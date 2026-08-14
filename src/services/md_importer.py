"""Markdown file importer — parses a task-per-line ``.md`` file into the repository."""

from __future__ import annotations

import uuid
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from .md_formatter import MarkdownTaskFormatter
from .md_parser import MarkdownTaskParser


class MarkdownImporter(QObject):
    """Import tasks from a Markdown file, one task line per row.

    Reuses the canonical :class:`MarkdownTaskParser` so imported lines obey
    the same grammar as the GUI editor; ``raw_md`` is rebuilt through
    :class:`MarkdownTaskFormatter` to keep round-trip stability.
    """

    scan_completed = Signal(int)  # task_count
    scan_error = Signal(str)  # error_msg

    def __init__(self, repository, parent=None) -> None:
        super().__init__(parent)
        self._repo = repository
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()

    def import_file(self, path: str, partition_id: str = "") -> int:
        """Import every non-empty line from ``path``. Returns imported count."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except OSError as exc:
            self.scan_error.emit(str(exc))
            return 0

        count = 0
        now = datetime.now()
        for line in lines:
            try:
                parsed = self._parser.parse(line)
            except ValueError as exc:
                self.scan_error.emit(f"无法解析: {line!r} — {exc}")
                continue
            task = self._repo.insert(self._build_task(parsed, line, partition_id, now))
            if task is not None:
                count += 1
        self.scan_completed.emit(count)
        return count

    def _build_task(self, parsed, raw_line: str, partition_id: str, now: datetime):
        """Assemble a Task from a ParsedTask — mirrors TaskService.create_task."""
        from ..models.task import Task

        task = Task(
            id=str(uuid.uuid4()),
            raw_md="",  # rebuilt below
            title=parsed.title,
            status=parsed.status,
            tags=parsed.tags,
            deadline_date=parsed.deadline_date,
            deadline_time=parsed.deadline_time,
            scheduled_date=parsed.scheduled_date,
            partition_id=partition_id,
            urgency=parsed.urgency,
            created_at=now,
            updated_at=now,
            activity_log=[{
                "ts": now.isoformat(),
                "content": "导入任务",
                "status": parsed.status.value,
                "progress": 100 if parsed.status.value == "DONE" else 0,
            }],
        )
        task.raw_md = self._formatter.format(task)
        return task
