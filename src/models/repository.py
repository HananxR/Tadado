"""TaskRepository — SQLite data access layer with FTS5 full-text search."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from typing import Optional

from .migrations import compute_activity_counts, migrate
from .task import Task
from .task_filter import SortCriterion, TaskFilter
from .task_status import TaskStatus

_TASK_COLUMNS = [
    "id", "raw_md", "title", "status", "priority", "tags",
    "scheduled_date", "deadline_date", "deadline_time",
    "created_at", "updated_at", "completed_at",
    "archived", "archived_at", "recurrence_rule", "parent_id",
    "partition_id", "notes",
    "activity_log",
    "progress",
    "activity_yesterday", "activity_today", "activity_last_week", "activity_week", "activity_last_month", "activity_month",
    "suspended",
]


def _row_to_task(row: tuple) -> Task:
    """Convert a database row tuple to a Task dataclass."""
    (
        id_, raw_md, title, status_str, _priority_int, tags_json,
        scheduled_str, deadline_str, deadline_time_str,
        created_str, updated_str, completed_str,
        archived_int, archived_str, recurrence, parent_id, partition_id, notes,
        activity_log_json, progress_int,
        ay, at, alw, aw, alm, am,
        suspended_int,
    ) = row

    return Task(
        id=id_,
        raw_md=raw_md,
        title=title,
        status=TaskStatus.from_string(status_str),
        tags=json.loads(tags_json) if tags_json else [],
        scheduled_date=_parse_date(scheduled_str),
        deadline_date=_parse_date(deadline_str),
        deadline_time=deadline_time_str,
        created_at=_parse_datetime(created_str),
        updated_at=_parse_datetime(updated_str),
        completed_at=_parse_datetime(completed_str),
        archived=bool(archived_int),
        archived_at=_parse_datetime(archived_str),
        recurrence_rule=recurrence,
        parent_id=parent_id,
        partition_id=partition_id,
        notes=notes,
        activity_log=json.loads(activity_log_json) if activity_log_json else [],
        progress=progress_int if progress_int else 0,
        activity_yesterday=ay if ay else 0,
        activity_today=at if at else 0,
        activity_last_week=alw if alw else 0,
        activity_week=aw if aw else 0,
        activity_last_month=alm if alm else 0,
        activity_month=am if am else 0,
        suspended=bool(suspended_int),
    )


def _task_to_row(task: Task) -> tuple:
    """Convert a Task dataclass to a database row tuple."""
    return (
        task.id,
        task.raw_md,
        task.title,
        task.status.value,
        0,  # priority (deprecated, kept for DB compat)
        json.dumps(task.tags, ensure_ascii=False),
        task.scheduled_date.isoformat() if task.scheduled_date else None,
        task.deadline_date.isoformat() if task.deadline_date else None,
        task.deadline_time,
        task.created_at.isoformat() if task.created_at else None,
        task.updated_at.isoformat() if task.updated_at else None,
        task.completed_at.isoformat() if task.completed_at else None,
        int(task.archived),
        task.archived_at.isoformat() if task.archived_at else None,
        task.recurrence_rule,
        task.parent_id,
        task.partition_id,
        task.notes,
        json.dumps(task.activity_log, ensure_ascii=False) if task.activity_log else "[]",
        task.progress,
        task.activity_yesterday,
        task.activity_today,
        task.activity_last_week,
        task.activity_week,
        task.activity_last_month,
        task.activity_month,
        int(task.suspended),
    )


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


class TaskRepository:
    """SQLite-backed repository for Task CRUD and queries."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the database and run pending migrations."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Repository not opened. Call open() first.")
        return self._conn

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def insert(self, task: Task) -> Task:
        """Insert a new task. Generates id / timestamps if missing."""
        if not task.id:
            task.id = str(uuid.uuid4())
        now_iso = datetime.now().isoformat()
        if not task.created_at:
            task.created_at = datetime.fromisoformat(now_iso)
        task.updated_at = datetime.fromisoformat(now_iso)
        self._recalc_activity_counts(task)

        row = _task_to_row(task)
        placeholders = ", ".join("?" * len(row))
        sql = f"INSERT INTO tasks ({', '.join(_TASK_COLUMNS)}) VALUES ({placeholders})"
        self.conn.execute(sql, row)
        self._update_fts(task)
        self.conn.commit()
        return task

    def update(self, task: Task) -> Task:
        """Update an existing task."""
        task.updated_at = datetime.now()
        self._recalc_activity_counts(task)
        row = _task_to_row(task)
        set_clause = ", ".join(f"{col}=?" for col in _TASK_COLUMNS)
        sql = f"UPDATE tasks SET {set_clause} WHERE id=?"
        self.conn.execute(sql, row + (task.id,))
        self._update_fts(task)
        self.conn.commit()
        return task

    def _recalc_activity_counts(self, task: Task) -> None:
        """Update the 6 activity count fields from activity_log timestamps."""
        log_json = json.dumps(task.activity_log, ensure_ascii=False) if task.activity_log else "[]"
        (task.activity_yesterday, task.activity_today,
         task.activity_week, task.activity_month,
         task.activity_last_week,
         task.activity_last_month) = compute_activity_counts(log_json)

    def delete(self, task_id: str) -> bool:
        """Delete a task by id. Returns True if a row was removed."""
        self.conn.execute("DELETE FROM tasks_fts WHERE rowid = (SELECT rowid FROM tasks WHERE id=?)", (task_id,))
        cursor = self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_by_id(self, task_id: str) -> Optional[Task]:
        """Retrieve a single task by id."""
        cols = ", ".join(_TASK_COLUMNS)
        row = self.conn.execute(
            f"SELECT {cols} FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        return _row_to_task(tuple(row)) if row else None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search(self, filter_: TaskFilter) -> list[Task]:
        """Query tasks with filtering, sorting, and pagination."""
        where_clauses: list[str] = []
        params: list = []

        # Archived filter (default: hide archived)
        if not filter_.show_archived:
            where_clauses.append("archived = 0")

        # Full-text search (FTS5 + LIKE fallback for CJK)
        if filter_.search_text:
            text = filter_.search_text
            where_clauses.append(
                "(rowid IN (SELECT rowid FROM tasks_fts WHERE tasks_fts MATCH ?)"
                " OR raw_md LIKE ? OR title LIKE ?)"
            )
            params.extend([text, f"%{text}%", f"%{text}%"])

        # Status filter
        if filter_.statuses is not None:
            status_values = [s.value for s in filter_.statuses]
            placeholders = ", ".join("?" for _ in status_values)
            where_clauses.append(f"status IN ({placeholders})")
            params.extend(status_values)

        # Tag filter (each tag must be present)
        if filter_.tags:
            for tag in filter_.tags:
                where_clauses.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

        # Partition filter
        if filter_.partition_id is not None:
            where_clauses.append("partition_id = ?")
            params.append(filter_.partition_id)

        # Date range filter
        if filter_.date_from:
            where_clauses.append(
                "(deadline_date >= ? OR scheduled_date >= ?"
                " OR (deadline_date IS NULL AND scheduled_date IS NULL))"
            )
            params.extend([filter_.date_from.isoformat(), filter_.date_from.isoformat()])
        if filter_.date_to:
            where_clauses.append(
                "(deadline_date <= ? OR scheduled_date <= ?"
                " OR (deadline_date IS NULL AND scheduled_date IS NULL))"
            )
            params.extend([filter_.date_to.isoformat(), filter_.date_to.isoformat()])

        # Created time range filter
        if filter_.created_from:
            where_clauses.append("created_at >= ?")
            params.append(filter_.created_from.isoformat())
        if filter_.created_to:
            where_clauses.append("created_at <= ?")
            params.append(filter_.created_to.isoformat())

        # Progress range filter
        if filter_.progress_min > 0 or filter_.progress_max < 100:
            where_clauses.append("progress >= ? AND progress <= ?")
            params.extend([filter_.progress_min, filter_.progress_max])

        # Overdue only
        if filter_.overdue_only:
            today = date.today().isoformat()
            where_clauses.append("deadline_date < ?")
            params.append(today)

        # Suspended filter (default: hide suspended)
        if not filter_.show_suspended:
            where_clauses.append("suspended = 0")
        elif filter_.suspended_only:
            where_clauses.append("suspended = 1")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Sorting
        order_clauses = self._build_order_clauses(filter_.sort_by)
        order_sql = f"ORDER BY {', '.join(order_clauses)}" if order_clauses else ""

        # Pagination
        limit_sql = ""
        if filter_.limit is not None:
            limit_sql = f"LIMIT {int(filter_.limit)}"
        offset_sql = f"OFFSET {int(filter_.offset)}" if filter_.offset else ""

        cols = ", ".join(_TASK_COLUMNS)
        sql = f"SELECT {cols} FROM tasks {where_sql} {order_sql} {limit_sql} {offset_sql}"
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_task(tuple(r)) for r in rows]

    def count(self, filter_: TaskFilter) -> int:
        """Count tasks matching the given filter."""
        where_clauses: list[str] = []
        params: list = []

        if not filter_.show_archived:
            where_clauses.append("archived = 0")
        if filter_.search_text:
            where_clauses.append(
                "id IN (SELECT rowid FROM tasks_fts WHERE tasks_fts MATCH ?)"
            )
            params.append(filter_.search_text)
        if filter_.statuses is not None:
            status_values = [s.value for s in filter_.statuses]
            placeholders = ", ".join("?" for _ in status_values)
            where_clauses.append(f"status IN ({placeholders})")
            params.extend(status_values)
        if filter_.partition_id is not None:
            where_clauses.append("partition_id = ?")
            params.append(filter_.partition_id)
        if filter_.date_from:
            where_clauses.append(
                "(deadline_date >= ? OR scheduled_date >= ?"
                " OR (deadline_date IS NULL AND scheduled_date IS NULL))"
            )
            params.extend([filter_.date_from.isoformat(), filter_.date_from.isoformat()])
        if filter_.date_to:
            where_clauses.append(
                "(deadline_date <= ? OR scheduled_date <= ?"
                " OR (deadline_date IS NULL AND scheduled_date IS NULL))"
            )
            params.extend([filter_.date_to.isoformat(), filter_.date_to.isoformat()])
        if filter_.created_from:
            where_clauses.append("created_at >= ?")
            params.append(filter_.created_from.isoformat())
        if filter_.created_to:
            where_clauses.append("created_at <= ?")
            params.append(filter_.created_to.isoformat())
        if filter_.progress_min > 0 or filter_.progress_max < 100:
            where_clauses.append("progress >= ? AND progress <= ?")
            params.extend([filter_.progress_min, filter_.progress_max])
        if filter_.overdue_only:
            from datetime import date as _date
            today = _date.today().isoformat()
            where_clauses.append("deadline_date < ?")
            params.append(today)
        if not filter_.show_suspended:
            where_clauses.append("suspended = 0")
        elif filter_.suspended_only:
            where_clauses.append("suspended = 1")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        row = self.conn.execute(f"SELECT COUNT(*) FROM tasks {where_sql}", params).fetchone()
        return row[0] if row else 0

    def get_all(self) -> list[Task]:
        """Return every task (including archived)."""
        cols = ", ".join(_TASK_COLUMNS)
        rows = self.conn.execute(f"SELECT {cols} FROM tasks ORDER BY created_at DESC").fetchall()
        return [_row_to_task(tuple(r)) for r in rows]

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def get_heatmap_data(self, year: int, tags: list[str] | None = None, partition_id: str | None = None) -> dict[date, int]:
        """Return a mapping of date -> task count for the heatmap, optionally filtered by tags and partition."""
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        query = """SELECT COALESCE(deadline_date, scheduled_date, created_at) as d, COUNT(*)
                   FROM tasks
                   WHERE d BETWEEN ? AND ? AND archived = 0"""
        params: list = [start, end]
        if tags:
            tag_clauses = " AND ".join("tags LIKE ?" for _ in tags)
            query += f" AND ({tag_clauses})"
            params.extend(f'%"{t}"%' for t in tags)
        if partition_id:
            query += " AND partition_id = ?"
            params.append(partition_id)
        query += " GROUP BY d"
        rows = self.conn.execute(query, params).fetchall()
        result: dict[date, int] = {}
        for row in rows:
            parsed = _parse_date(row[0])
            if parsed:
                result[parsed] = row[1]
        return result

    def get_heatmap_activity_data(self, year: int, tags: list[str] | None = None, partition_id: str | None = None) -> tuple[dict[date, int], dict[date, int]]:
        """Return (entry_counts, task_counts) per date, based on activity_log timestamps."""
        query = """SELECT id, activity_log FROM tasks WHERE archived = 0"""
        params: list = []
        if tags:
            tag_clauses = " AND ".join("tags LIKE ?" for _ in tags)
            query += f" AND ({tag_clauses})"
            params.extend(f'%"{t}"%' for t in tags)
        if partition_id:
            query += " AND partition_id = ?"
            params.append(partition_id)
        rows = self.conn.execute(query, params).fetchall()
        entry_counts: dict[date, int] = {}
        task_counts: dict[date, set[str]] = {}
        for task_id, activity_log_json in rows:
            if not activity_log_json:
                continue
            try:
                entries = json.loads(activity_log_json)
            except (json.JSONDecodeError, TypeError):
                continue
            for entry in entries:
                ts_str = entry.get("ts", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue
                if ts.date().year == year:
                    d = ts.date()
                    entry_counts[d] = entry_counts.get(d, 0) + 1
                    task_counts.setdefault(d, set()).add(task_id)
        task_count_result = {d: len(ids) for d, ids in task_counts.items()}
        return entry_counts, task_count_result

    def get_heatmap_tag_breakdown(self, year: int, d: date, partition_id: str | None = None) -> dict[str, int]:
        """Return per-tag task counts for a specific date."""
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        query = """SELECT tags FROM tasks
                   WHERE COALESCE(deadline_date, scheduled_date, created_at) = ?
                     AND COALESCE(deadline_date, scheduled_date, created_at) BETWEEN ? AND ?
                     AND archived = 0"""
        params: list = [d.isoformat(), start, end]
        if partition_id:
            query += " AND partition_id = ?"
            params.append(partition_id)
        rows = self.conn.execute(query, params).fetchall()
        result: dict[str, int] = {}
        for (tags_json,) in rows:
            if tags_json:
                for t in json.loads(tags_json):
                    result[t] = result.get(t, 0) + 1
        return result

    # ------------------------------------------------------------------
    # Partition CRUD
    # ------------------------------------------------------------------

    def get_all_partitions(self) -> list[dict]:
        """Return all partitions ordered by sort_order."""
        rows = self.conn.execute(
            "SELECT id, name, sort_order, password, archive_days, archive_enabled, created_at FROM partitions ORDER BY sort_order"
        ).fetchall()
        return [
            {"id": r[0], "name": r[1], "sort_order": r[2], "password": r[3],
             "archive_days": r[4], "archive_enabled": r[5], "created_at": r[6]}
            for r in rows
        ]

    def check_partition_password(self, partition_id: str) -> tuple[bool, str]:
        """Return (has_password, password_hash_or_empty)."""
        row = self.conn.execute(
            "SELECT password FROM partitions WHERE id = ?", (partition_id,)
        ).fetchone()
        if row and row[0]:
            return True, row[0]
        return False, ""

    def set_partition_password(self, partition_id: str, password: str) -> None:
        """Set or clear a partition password."""
        self.conn.execute(
            "UPDATE partitions SET password = ? WHERE id = ?",
            (password, partition_id),
        )
        self.conn.commit()

    def update_partition_archive_days(self, partition_id: str, days: int) -> None:
        """Set the archive-after-completion days for a partition."""
        self.conn.execute(
            "UPDATE partitions SET archive_days = ? WHERE id = ?",
            (days, partition_id),
        )
        self.conn.commit()

    def update_partition_archive_enabled(self, partition_id: str, enabled: int) -> None:
        """Set whether auto-archive is enabled for a partition."""
        self.conn.execute(
            "UPDATE partitions SET archive_enabled = ? WHERE id = ?",
            (enabled, partition_id),
        )
        self.conn.commit()

    def count_tasks_in_partition(self, partition_id: str) -> int:
        """Return the number of tasks in a partition."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE partition_id = ?", (partition_id,)
        ).fetchone()
        return row[0] if row else 0

    def get_partition_name_map(self) -> dict[str, str]:
        """Return a mapping of partition_id → partition name."""
        rows = self.conn.execute(
            "SELECT id, name FROM partitions"
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def upsert_partition(self, name: str, partition_id: str = "", sort_order: int = 0) -> dict:
        """Insert or rename a partition. Returns the partition dict."""
        import uuid as _uuid
        if partition_id:
            self.conn.execute(
                "UPDATE partitions SET name = ?, sort_order = ? WHERE id = ?",
                (name, sort_order, partition_id),
            )
        else:
            partition_id = str(_uuid.uuid4())
            self.conn.execute(
                "INSERT INTO partitions (id, name, sort_order, created_at) VALUES (?, ?, ?, ?)",
                (partition_id, name, sort_order, datetime.now().isoformat()),
            )
        self.conn.commit()
        return {"id": partition_id, "name": name, "sort_order": sort_order}

    def delete_partition(self, partition_id: str) -> bool:
        """Delete a partition. Sets partition_id=NULL on affected tasks."""
        self.conn.execute(
            "UPDATE tasks SET partition_id = NULL WHERE partition_id = ?",
            (partition_id,),
        )
        self.conn.execute("DELETE FROM partitions WHERE id = ?", (partition_id,))
        self.conn.commit()
        return True

    def get_all_tags(self, partition_id: str | None = None) -> list[str]:
        """Return all unique tags from non-archived tasks, optionally filtered by partition."""
        query = "SELECT DISTINCT tags FROM tasks WHERE archived = 0"
        params: list = []
        if partition_id:
            query += " AND partition_id = ?"
            params.append(partition_id)
        rows = self.conn.execute(query, params).fetchall()
        tag_set: set[str] = set()
        for (tags_json,) in rows:
            if tags_json:
                for t in json.loads(tags_json):
                    tag_set.add(t)
        return sorted(tag_set)

    def get_status_counts(
        self, partition_id: str | None = None,
        date_from: date | None = None, date_to: date | None = None,
    ) -> dict[TaskStatus, int]:
        """Return counts grouped by task status, excluding suspended and archived."""
        clauses = ["archived=0", "suspended=0"]
        params: list = []
        if partition_id:
            clauses.append("partition_id=?")
            params.append(partition_id)
        if date_from:
            clauses.append("(deadline_date >= ? OR scheduled_date >= ? OR (deadline_date IS NULL AND scheduled_date IS NULL))")
            params.extend([date_from.isoformat(), date_from.isoformat()])
        if date_to:
            clauses.append("(deadline_date <= ? OR scheduled_date <= ? OR (deadline_date IS NULL AND scheduled_date IS NULL))")
            params.extend([date_to.isoformat(), date_to.isoformat()])
        where = " AND ".join(clauses)
        rows = self.conn.execute(
            f"SELECT status, COUNT(*) FROM tasks WHERE {where} GROUP BY status", params
        ).fetchall()
        return {TaskStatus.from_string(r[0]): r[1] for r in rows}

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def batch_update_status(self, task_ids: list[str], new_status: TaskStatus) -> int:
        """Bulk update status for multiple tasks, recording activity_log entries."""
        from ..services.md_formatter import MarkdownTaskFormatter

        formatter = MarkdownTaskFormatter()
        now = datetime.now().isoformat()
        status_value = new_status.value
        count = 0

        for task_id in task_ids:
            task = self.get_by_id(task_id)
            if task is None:
                continue
            old_status = task.status.display_name
            entry = {
                "ts": now,
                "content": f"[批量操作] 状态变更: {old_status} -> {new_status.display_name}",
                "status": status_value,
                "progress": task.progress,
            }
            log = list(task.activity_log) + [entry]
            self.conn.execute(
                "UPDATE tasks SET status=?, activity_log=?, updated_at=? WHERE id=?",
                (status_value, json.dumps(log, ensure_ascii=False), now, task_id),
            )
            # Update task for FTS and raw_md sync
            task.status = new_status
            task.activity_log = log
            task.updated_at = _parse_datetime(now)
            task.raw_md = formatter.format(task)
            self.conn.execute(
                "UPDATE tasks SET raw_md=? WHERE id=?",
                (task.raw_md, task_id),
            )
            self._update_fts(task)
            self._recalc_activity_counts(task)
            self.conn.execute(
                "UPDATE tasks SET activity_yesterday=?, activity_today=?, activity_last_week=?, activity_week=?, activity_last_month=?, activity_month=? WHERE id=?",
                (task.activity_yesterday, task.activity_today, task.activity_last_week, task.activity_week, task.activity_last_month, task.activity_month, task_id),
            )
            count += 1

        self.conn.commit()
        return count

    def batch_delete(self, task_ids: list[str]) -> int:
        """Permanently delete multiple tasks and their FTS entries."""
        placeholders = ", ".join("?" for _ in task_ids)
        self.conn.execute(
            f"DELETE FROM tasks_fts WHERE rowid IN (SELECT rowid FROM tasks WHERE id IN ({placeholders}))",
            task_ids,
        )
        cursor = self.conn.execute(
            f"DELETE FROM tasks WHERE id IN ({placeholders})", task_ids
        )
        self.conn.commit()
        return cursor.rowcount

    def batch_suspend(self, task_ids: list[str]) -> int:
        """Suspend multiple tasks (exclude from statistics)."""
        now = datetime.now().isoformat()
        count = 0
        for task_id in task_ids:
            task = self.get_by_id(task_id)
            if task is None:
                continue
            entry = {
                "ts": now,
                "content": "[批量操作] 任务已中止",
                "status": task.status.value,
                "progress": task.progress,
            }
            log = list(task.activity_log) + [entry]
            self.conn.execute(
                "UPDATE tasks SET suspended=1, activity_log=?, updated_at=? WHERE id=?",
                (json.dumps(log, ensure_ascii=False), now, task_id),
            )
            task.activity_log = log
            self._update_fts(task)
            self._recalc_activity_counts(task)
            self.conn.execute(
                "UPDATE tasks SET activity_yesterday=?, activity_today=?, activity_last_week=?, activity_week=?, activity_last_month=?, activity_month=? WHERE id=?",
                (task.activity_yesterday, task.activity_today, task.activity_last_week, task.activity_week, task.activity_last_month, task.activity_month, task_id),
            )
            count += 1
        self.conn.commit()
        return count

    def batch_restart(self, task_ids: list[str]) -> int:
        """Restart multiple suspended tasks (re-include in statistics)."""
        now = datetime.now().isoformat()
        count = 0
        for task_id in task_ids:
            task = self.get_by_id(task_id)
            if task is None:
                continue
            entry = {
                "ts": now,
                "content": "[批量操作] 任务已恢复",
                "status": task.status.value,
                "progress": task.progress,
            }
            log = list(task.activity_log) + [entry]
            self.conn.execute(
                "UPDATE tasks SET suspended=0, activity_log=?, updated_at=? WHERE id=?",
                (json.dumps(log, ensure_ascii=False), now, task_id),
            )
            task.activity_log = log
            self._update_fts(task)
            self._recalc_activity_counts(task)
            self.conn.execute(
                "UPDATE tasks SET activity_yesterday=?, activity_today=?, activity_last_week=?, activity_week=?, activity_last_month=?, activity_month=? WHERE id=?",
                (task.activity_yesterday, task.activity_today, task.activity_last_week, task.activity_week, task.activity_last_month, task.activity_month, task_id),
            )
            count += 1
        self.conn.commit()
        return count

    def batch_postpone(self, task_ids: list[str], days: int) -> int:
        """Postpone deadline for multiple tasks by N days, recording activity_log."""
        from datetime import timedelta

        from ..services.md_formatter import MarkdownTaskFormatter

        formatter = MarkdownTaskFormatter()
        now = datetime.now().isoformat()
        count = 0

        for task_id in task_ids:
            task = self.get_by_id(task_id)
            if task is None:
                continue

            old_deadline = task.deadline_date.isoformat() if task.deadline_date else "无"
            if task.deadline_date:
                new_date = task.deadline_date + timedelta(days=days)
            else:
                new_date = date.today() + timedelta(days=days)
            new_deadline = new_date.isoformat()

            entry = {
                "ts": now,
                "content": f"[批量操作] 延后处理: 截止时间 {old_deadline} -> {new_deadline}（+{days}天）",
                "status": task.status.value,
                "progress": task.progress,
            }
            log = list(task.activity_log) + [entry]

            self.conn.execute(
                "UPDATE tasks SET deadline_date=?, activity_log=?, updated_at=? WHERE id=?",
                (new_deadline, json.dumps(log, ensure_ascii=False), now, task_id),
            )
            task.deadline_date = new_date
            task.activity_log = log
            task.updated_at = _parse_datetime(now)
            task.raw_md = formatter.format(task)
            self.conn.execute(
                "UPDATE tasks SET raw_md=? WHERE id=?", (task.raw_md, task_id)
            )
            self._update_fts(task)
            self._recalc_activity_counts(task)
            self.conn.execute(
                "UPDATE tasks SET activity_yesterday=?, activity_today=?, activity_last_week=?, activity_week=?, activity_last_month=?, activity_month=? WHERE id=?",
                (task.activity_yesterday, task.activity_today, task.activity_last_week, task.activity_week, task.activity_last_month, task.activity_month, task_id),
            )
            count += 1

        self.conn.commit()
        # Refresh overdue status after postponing deadlines
        self.refresh_overdue_status()
        return count

    def count_by_status(self, task_ids: list[str]) -> dict[str, int]:
        """Return status distribution for a specific set of tasks."""
        if not task_ids:
            return {"overdue": 0, "doing": 0, "done": 0, "todo": 0}
        placeholders = ", ".join("?" for _ in task_ids)
        rows = self.conn.execute(
            f"SELECT status, COUNT(*) FROM tasks WHERE id IN ({placeholders}) GROUP BY status",
            task_ids,
        ).fetchall()
        result = {s: 0 for s in ("overdue", "doing", "done", "todo")}
        for status_str, cnt in rows:
            key = status_str.lower()
            if key in result:
                result[key] = cnt
        return result

    # ------------------------------------------------------------------
    # Reminder helpers (Phase 2)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Reminder helpers (Phase 2)
    # ------------------------------------------------------------------

    def get_due_today(self) -> list[Task]:
        today = date.today().isoformat()
        cols = ", ".join(_TASK_COLUMNS)
        rows = self.conn.execute(
            f"SELECT {cols} FROM tasks WHERE deadline_date=? AND archived=0 AND status!='DONE'",
            (today,),
        ).fetchall()
        return [_row_to_task(tuple(r)) for r in rows]

    def get_due_this_week(self) -> list[Task]:
        today = date.today()
        end = today.isoformat()
        start = (today.replace(day=1)).isoformat()  # simplified; Phase 2 refines
        cols = ", ".join(_TASK_COLUMNS)
        rows = self.conn.execute(
            f"SELECT {cols} FROM tasks WHERE deadline_date BETWEEN ? AND ? AND archived=0 AND status!='DONE'",
            (start, end),
        ).fetchall()
        return [_row_to_task(tuple(r)) for r in rows]

    def get_overdue(self) -> list[Task]:
        today = date.today().isoformat()
        cols = ", ".join(_TASK_COLUMNS)
        rows = self.conn.execute(
            f"SELECT {cols} FROM tasks WHERE deadline_date < ? AND archived=0 AND status!='DONE'",
            (today,),
        ).fetchall()
        return [_row_to_task(tuple(r)) for r in rows]

    # ------------------------------------------------------------------
    # Overdue status refresh
    # ------------------------------------------------------------------

    def refresh_overdue_status(self) -> list[tuple[Task, TaskStatus]]:
        """Scan all tasks and auto-set or revert OVERDUE status.

        Returns a list of (task, old_status) for each changed task
        so callers can emit ``task_status_changed`` signals.
        """
        from ..services.md_formatter import MarkdownTaskFormatter

        formatter = MarkdownTaskFormatter()
        changed: list[tuple[Task, TaskStatus]] = []
        today_iso = date.today().isoformat()
        cols = ", ".join(_TASK_COLUMNS)

        # Tasks past deadline that are not yet OVERDUE or DONE → OVERDUE
        rows = self.conn.execute(
            f"SELECT {cols} FROM tasks WHERE deadline_date < ? "
            "AND deadline_date IS NOT NULL AND archived = 0 "
            "AND status NOT IN ('DONE', 'OVERDUE')",
            (today_iso,),
        ).fetchall()
        for row in rows:
            task = _row_to_task(tuple(row))
            old_status = task.status
            task.status = TaskStatus.OVERDUE
            task.raw_md = formatter.format(task)
            self.update(task)
            changed.append((task, old_status))

        # OVERDUE tasks whose deadline is now in the future → revert to DOING
        rows = self.conn.execute(
            f"SELECT {cols} FROM tasks WHERE status = 'OVERDUE' "
            "AND (deadline_date >= ? OR deadline_date IS NULL)",
            (today_iso,),
        ).fetchall()
        for row in rows:
            task = _row_to_task(tuple(row))
            old_status = task.status
            task.status = TaskStatus.DOING
            task.raw_md = formatter.format(task)
            self.update(task)
            changed.append((task, old_status))

        return changed

    # ------------------------------------------------------------------
    # Archive helpers (Phase 2)
    # ------------------------------------------------------------------

    def get_tasks_for_archive(self, cutoff_date: date, partition_id: str | None = None) -> list[Task]:
        cols = ", ".join(_TASK_COLUMNS)
        if partition_id:
            rows = self.conn.execute(
                f"SELECT {cols} FROM tasks WHERE status='DONE' AND completed_at <= ? "
                "AND archived=0 AND partition_id = ?",
                (cutoff_date.isoformat(), partition_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"SELECT {cols} FROM tasks WHERE status='DONE' AND completed_at <= ? AND archived=0",
                (cutoff_date.isoformat(),),
            ).fetchall()
        return [_row_to_task(tuple(r)) for r in rows]

    def archive_batch(self, task_ids: list[str]) -> int:
        now = datetime.now().isoformat()
        placeholders = ", ".join("?" for _ in task_ids)
        cursor = self.conn.execute(
            f"UPDATE tasks SET archived=1, archived_at=? WHERE id IN ({placeholders})",
            [now] + task_ids,
        )
        self.conn.commit()
        return cursor.rowcount

    def get_last_archive_time(self) -> datetime | None:
        """Return the most recent archive timestamp, or None if never archived."""
        row = self.conn.execute(
            "SELECT MAX(archived_at) FROM tasks WHERE archived = 1"
        ).fetchone()
        if row and row[0]:
            return _parse_datetime(row[0])
        return None

    # ------------------------------------------------------------------
    # Notification log (Phase 2)
    # ------------------------------------------------------------------

    def notification_sent(self, task_id: str, interval_minutes: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM notification_log WHERE task_id=? AND interval_minutes=?",
            (task_id, interval_minutes),
        ).fetchone()
        return row is not None

    def mark_notification_sent(self, task_id: str, interval_minutes: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO notification_log(task_id, interval_minutes, sent_at) VALUES (?, ?, ?)",
            (task_id, interval_minutes, datetime.now().isoformat()),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_fts(self, task: Task) -> None:
        """Sync the FTS5 index for a single task."""
        self.conn.execute(
            "INSERT OR REPLACE INTO tasks_fts(rowid, raw_md, title, notes, tags) "
            "SELECT rowid, raw_md, title, notes, tags FROM tasks WHERE id=?",
            (task.id,),
        )

    @staticmethod
    def _build_order_clauses(sort_by: list[SortCriterion]) -> list[str]:
        _field_map = {
            "deadline": "deadline_date",
            "created": "created_at",
            "status": "status",
            "title": "title",
            "scheduled": "scheduled_date",
            "urgency": "urgency",
            "activity_yesterday": "activity_yesterday",
            "activity_today": "activity_today",
            "activity_last_week": "activity_last_week",
            "activity_week": "activity_week",
            "activity_last_month": "activity_last_month",
            "activity_month": "activity_month",
        }
        clauses: list[str] = []
        for sc in sort_by:
            col = _field_map.get(sc.field, sc.field)
            if sc.field == "status":
                # Custom order: OVERDUE > DOING > TODO > DONE
                clauses.append(
                    "CASE status WHEN 'OVERDUE' THEN 1 "
                    "WHEN 'DOING' THEN 2 WHEN 'TODO' THEN 3 WHEN 'DONE' THEN 4 ELSE 5 END "
                    + ("ASC" if sc.ascending else "DESC")
                )
            elif sc.field == "urgency":
                # "ascending" = most urgent first (score DESC, progress DESC, created ASC)
                urgency_expr = (
                    "CASE WHEN status = 'DONE' THEN -9999 "
                    "WHEN deadline_date IS NULL THEN -9998 "
                    "ELSE julianday('now') - julianday(deadline_date) END"
                )
                if sc.ascending:
                    clauses.append(f"{urgency_expr} DESC")
                    clauses.append("progress DESC")
                    clauses.append("created_at ASC")
                else:
                    clauses.append(f"{urgency_expr} ASC")
                    clauses.append("progress ASC")
                    clauses.append("created_at DESC")
            else:
                direction = "ASC" if sc.ascending else "DESC"
                clauses.append(f"{col} {direction}")
        return clauses
