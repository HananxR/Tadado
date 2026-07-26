"""TaskService — single seam between UI and data layers.

All task CRUD, batch operations, queries, partition management, tags,
and heatmap data flow through this module.  It owns the Markdown parser,
formatter, and signal bus so that callers only need one dependency.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from ..models.partition import Partition
from ..models.task import Task
from ..models.task_filter import TaskFilter
from ..models.task_status import TaskStatus
from ..utils.signal_bus import SignalBus, get_signal_bus
from .md_formatter import MarkdownTaskFormatter
from .md_parser import MarkdownTaskParser, ParsedTask

_log = logging.getLogger("runlog")


class TaskService:
    """Facade over TaskRepository + Markdown formatter/parser + SignalBus.

    Every UI component that needs task data talks to this service instead
    of calling the repository directly.  The service enforces invariants,
    regenerates ``raw_md`` after mutations, emits signals, and logs at
    operation boundaries.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(
        self,
        repository,  # TaskRepository (lazy import to avoid circular dep)
        signal_bus: SignalBus | None = None,
    ) -> None:
        self._repo = repository
        self._bus = signal_bus if signal_bus is not None else get_signal_bus()
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()
        # Handle immediate archiving when archive_days=0
        self._bus.task_status_changed.connect(self._on_status_changed_for_archive)
        self._bus.task_created.connect(self._on_task_created_for_archive)

    # ------------------------------------------------------------------
    # Task CRUD
    # ------------------------------------------------------------------

    def create_task(self, raw_md: str, partition_id: str = "") -> Task:
        """Parse Markdown → create Task → insert → emit signal → return Task."""
        parsed = self._parser.parse(raw_md)
        now = datetime.now()
        task = Task(
            id=str(uuid.uuid4()),
            raw_md="",  # rebuilt below
            title=parsed.title,
            status=parsed.status,
            tags=parsed.tags,
            deadline_date=parsed.deadline_date,
            deadline_time=parsed.deadline_time,
            scheduled_date=parsed.scheduled_date,
            partition_id=partition_id or "",
            urgency=parsed.urgency,
            created_at=now,
            updated_at=now,
            activity_log=[{
                "ts": now.isoformat(),
                "content": "创建任务",
                "status": parsed.status.value,
                "progress": 100 if parsed.status == TaskStatus.DONE else 0,
            }],
        )
        task.raw_md = self._formatter.format(task)
        task = self._repo.insert(task)
        self._bus.task_created.emit(task)
        _log.info("TaskService: created task id=%s title=%r", task.id, task.title)
        return task

    def update_task(self, task: Task) -> Task:
        """Update task → rebuild raw_md → emit task_updated → return updated task."""
        task.raw_md = self._formatter.format(task)
        task = self._repo.update(task)
        self._bus.task_updated.emit(task)
        _log.info("TaskService: updated task id=%s title=%r", task.id, task.title)
        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete task by id → emit task_deleted → return True if removed."""
        removed = self._repo.delete(task_id)
        if removed:
            self._bus.task_deleted.emit(task_id)
            _log.info("TaskService: deleted task id=%s", task_id)
        return removed

    def get_task(self, task_id: str) -> Task | None:
        """Retrieve a single task by id."""
        return self._repo.get_by_id(task_id)

    # ------------------------------------------------------------------
    # Task status change (with signal)
    # ------------------------------------------------------------------

    def change_task_status(self, task: Task, new_status: TaskStatus) -> Task:
        """Change a task's status → rebuild raw_md → emit task_status_changed."""
        old_status = task.status
        task.status = new_status
        if new_status == TaskStatus.DONE:
            task.progress = 100
            task.completed_at = date.today()
        task.raw_md = self._formatter.format(task)
        task = self._repo.update(task)
        self._bus.task_status_changed.emit(task, old_status)
        _log.info(
            "TaskService: status change id=%s %s→%s",
            task.id, old_status.value, new_status.value,
        )
        return task

    # ------------------------------------------------------------------
    # Internal — immediate archive on DONE
    # ------------------------------------------------------------------

    def _on_task_created_for_archive(self, task: Task) -> None:
        """Check immediate archive when a new task is created as DONE."""
        self._check_immediate_archive(task)

    def _on_status_changed_for_archive(self, task: Task, old_status: TaskStatus) -> None:
        """Archive when DONE; un-archive when status changes FROM DONE."""
        if old_status == TaskStatus.DONE and task.status != TaskStatus.DONE:
            self._unarchive_if_needed(task)
        self._check_immediate_archive(task)

    def _unarchive_if_needed(self, task: Task) -> None:
        """Un-archive task when status moves FROM DONE to something else."""
        if not task.archived:
            return
        self._repo.conn.execute(
            "UPDATE tasks SET archived=0 WHERE id=?", (task.id,)
        )
        self._repo.conn.commit()
        task.archived = False
        _log.info("TaskService: un-archived task id=%s (status no longer DONE)", task.id)

    def _check_immediate_archive(self, task: Task) -> None:
        """Archive task if it's DONE and its partition has archive_days=0."""
        if task.status != TaskStatus.DONE:
            return
        if not task.partition_id:
            return
        partitions = self._repo.get_all_partitions()
        for p in partitions:
            if p["id"] == task.partition_id:
                if p.get("archive_days", 0) == 0:
                    self._repo.archive_batch([task.id])
                    self._bus.archive_completed.emit(1)
                    _log.info(
                        "TaskService: immediate archive id=%s (archive_days=0)",
                        task.id,
                    )
                break

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def batch_update_status(self, task_ids: list[str], new_status: TaskStatus) -> int:
        """Bulk status update → rebuild raw_md → emit signal → return count."""
        if not task_ids:
            return 0
        count = self._repo.batch_update_status(
            task_ids, new_status, formatter=self._formatter,
        )
        # Archive/un-archive as needed
        for tid in task_ids:
            task = self._repo.get_by_id(tid)
            if not task:
                continue
            if new_status == TaskStatus.DONE:
                self._check_immediate_archive(task)
            elif task.archived and new_status != TaskStatus.DONE:
                self._unarchive_if_needed(task)
        self._bus.batch_operation_completed.emit({
            "action": "batch_update_status",
            "status": new_status.value,
            "count": count,
        })
        _log.info("TaskService: batch_update_status %d tasks → %s", count, new_status.value)
        return count

    def batch_update_urgency(self, task_ids: list[str], urgency: int) -> int:
        """Bulk urgency update → rebuild raw_md → emit signal → return count."""
        if not task_ids:
            return 0
        count = self._repo.batch_update_urgency(
            task_ids, urgency, formatter=self._formatter,
        )
        self._bus.batch_operation_completed.emit({
            "action": "batch_update_urgency",
            "urgency": urgency,
            "count": count,
        })
        _log.info("TaskService: batch_update_urgency %d tasks → %d", count, urgency)
        return count

    def batch_delete(self, task_ids: list[str]) -> int:
        """Bulk delete → emit signal → return count."""
        if not task_ids:
            return 0
        count = self._repo.batch_delete(task_ids)
        self._bus.batch_operation_completed.emit({
            "action": "batch_delete",
            "count": count,
        })
        _log.info("TaskService: batch_delete %d tasks", count)
        return count

    def batch_suspend(self, task_ids: list[str]) -> int:
        """Bulk suspend → emit signal → return count."""
        if not task_ids:
            return 0
        count = self._repo.batch_suspend(task_ids)
        self._bus.batch_operation_completed.emit({
            "action": "batch_suspend",
            "count": count,
        })
        _log.info("TaskService: batch_suspend %d tasks", count)
        return count

    def batch_restart(self, task_ids: list[str]) -> int:
        """Bulk restart (unsuspend) → emit signal → return count."""
        if not task_ids:
            return 0
        count = self._repo.batch_restart(task_ids)
        self._bus.batch_operation_completed.emit({
            "action": "batch_restart",
            "count": count,
        })
        _log.info("TaskService: batch_restart %d tasks", count)
        return count

    def batch_postpone(self, task_ids: list[str], days: int) -> int:
        """Postpone deadlines → rebuild raw_md → emit signal → return count."""
        if not task_ids:
            return 0
        count = self._repo.batch_postpone(
            task_ids, days, formatter=self._formatter,
        )
        self._bus.batch_operation_completed.emit({
            "action": "batch_postpone",
            "days": days,
            "count": count,
        })
        _log.info("TaskService: batch_postpone %d tasks +%dd", count, days)
        return count

    def batch_move_partition(self, task_ids: list[str], to_partition_id: str) -> int:
        """Move tasks to another partition → emit signal → return count."""
        if not task_ids:
            return 0
        count = self._repo.batch_move_partition(task_ids, to_partition_id)
        self._bus.batch_operation_completed.emit({
            "action": "batch_move_partition",
            "count": count,
        })
        _log.info("TaskService: batch_move_partition %d tasks", count)
        return count

    def archive_batch(self, task_ids: list[str]) -> int:
        """Archive completed tasks → emit archive_completed → return count."""
        if not task_ids:
            return 0
        count = self._repo.archive_batch(task_ids)
        self._bus.archive_completed.emit(count)
        _log.info("TaskService: archive_batch %d tasks", count)
        return count

    def ensure_default_partition(self) -> str:
        """Ensure at least one partition exists; return its id."""
        return self._repo.ensure_default_partition()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search(self, filter_: TaskFilter) -> list[Task]:
        """Query tasks with filtering, sorting, and pagination."""
        return self._repo.search(filter_)

    def search_with_total(self, filter_: TaskFilter) -> tuple[list[Task], int]:
        """Query tasks + total count."""
        return self._repo.search_with_total(filter_)

    def get_all(self) -> list[Task]:
        """Return every task (including archived)."""
        return self._repo.get_all()

    def count(self, filter_: TaskFilter) -> int:
        """Count tasks matching the filter."""
        return self._repo.count(filter_)

    def get_status_counts(
        self,
        partition_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[TaskStatus, int]:
        """Return counts grouped by status (excluding suspended + archived)."""
        return self._repo.get_status_counts(
            partition_id=partition_id,
            date_from=date_from,
            date_to=date_to,
        )

    # ------------------------------------------------------------------
    # Partitions
    # ------------------------------------------------------------------

    def get_all_partitions(self) -> list[dict]:
        """Return all partitions ordered by sort_order."""
        return self._repo.get_all_partitions()

    def get_partition_name_map(self) -> dict[str, str]:
        """Return {partition_id: partition_name}."""
        return self._repo.get_partition_name_map()

    def upsert_partition(self, name: str, partition_id: str = "") -> dict:
        """Insert or rename a partition → emit partitions_changed."""
        result = self._repo.upsert_partition(name, partition_id)
        self._bus.partitions_changed.emit()
        _log.info("TaskService: upsert_partition %r id=%s", name, result["id"])
        return result

    def delete_partition(self, partition_id: str) -> bool:
        """Delete a partition → emit partitions_changed."""
        result = self._repo.delete_partition(partition_id)
        self._bus.partitions_changed.emit()
        _log.info("TaskService: delete_partition id=%s", partition_id)
        return result

    def set_partition_password(self, partition_id: str, password: str) -> None:
        """Set or clear a partition password."""
        self._repo.set_partition_password(partition_id, password)
        _log.info(
            "TaskService: partition password %s id=%s",
            "set" if password else "cleared", partition_id,
        )

    def check_partition_password(self, partition_id: str) -> tuple[bool, str]:
        """Return (has_password, password_hash_or_empty)."""
        return self._repo.check_partition_password(partition_id)

    def count_tasks_in_partition(self, partition_id: str) -> int:
        """Return number of tasks in a partition."""
        return self._repo.count_tasks_in_partition(partition_id)

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def get_all_tags(self, partition_id: str | None = None) -> list[str]:
        """Return sorted unique tags from non-archived tasks."""
        return self._repo.get_all_tags(partition_id)

    def get_all_tags_with_counts(self, partition_id: str | None = None) -> list[tuple[str, int]]:
        """Return (tag, count) sorted by count desc."""
        return self._repo.get_all_tags_with_counts(partition_id)

    def get_tasks_by_tag(self, tag: str, partition_id: str | None = None) -> list[Task]:
        """Return all tasks (including archived) containing the given tag."""
        return self._repo.get_tasks_by_tag(tag, partition_id)

    def get_tasks_by_tags(self, tags: set[str], partition_id: str | None = None) -> list[Task]:
        """Return all tasks (including archived) containing ANY of the given tags."""
        return self._repo.get_tasks_by_tags(tags, partition_id)

    # ------------------------------------------------------------------
    # Heatmap
    # ------------------------------------------------------------------

    def get_heatmap_activity_data(
        self,
        year: int,
        tags: list[str] | None = None,
        partition_id: str | None = None,
    ) -> tuple[dict[date, int], dict[date, int]]:
        """Return (entry_counts, task_counts) per date from activity_log timestamps."""
        return self._repo.get_heatmap_activity_data(year, tags, partition_id)

    # ------------------------------------------------------------------
    # Overdue refresh (delegated — called by TaskScheduler)
    # ------------------------------------------------------------------

    def refresh_overdue_status(self) -> list[tuple[Task, TaskStatus]]:
        """Scan tasks and auto-set/revert OVERDUE → emit task_status_changed per task."""
        return self._repo.refresh_overdue_status(formatter=self._formatter)

    # ------------------------------------------------------------------
    # Formatting (convenience)
    # ------------------------------------------------------------------

    def format_task(self, task: Task) -> str:
        """Return the canonical Markdown line for a task."""
        return self._formatter.format(task)

    def parse_markdown(self, raw_md: str) -> ParsedTask:
        """Parse a Markdown line into a ParsedTask."""
        return self._parser.parse(raw_md)
