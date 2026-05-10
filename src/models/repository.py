"""TaskRepository — SQLite data access layer with FTS5 full-text search."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from typing import Optional

from .priority import Priority
from .task import Task
from .task_filter import SortCriterion, TaskFilter
from .task_status import TaskStatus

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    raw_md TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'TODO',
    priority INTEGER NOT NULL DEFAULT 0,
    tags TEXT DEFAULT '[]',
    scheduled_date TEXT,
    deadline_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    archived_at TEXT,
    recurrence_rule TEXT,
    parent_id TEXT,
    notes TEXT DEFAULT '',
    FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS notification_log (
    task_id TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (task_id, interval_minutes)
);

CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
    raw_md, title, notes, tags, content='tasks', tokenize='unicode61'
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline_date);
CREATE INDEX IF NOT EXISTS idx_tasks_scheduled ON tasks(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_archived ON tasks(archived);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
"""

_TASK_COLUMNS = [
    "id", "raw_md", "title", "status", "priority", "tags",
    "scheduled_date", "deadline_date",
    "created_at", "updated_at", "completed_at",
    "archived", "archived_at", "recurrence_rule", "parent_id", "notes",
]


def _row_to_task(row: tuple) -> Task:
    """Convert a database row tuple to a Task dataclass."""
    (
        id_, raw_md, title, status_str, priority_int, tags_json,
        scheduled_str, deadline_str,
        created_str, updated_str, completed_str,
        archived_int, archived_str, recurrence, parent_id, notes,
    ) = row

    return Task(
        id=id_,
        raw_md=raw_md,
        title=title,
        status=TaskStatus.from_string(status_str),
        priority=Priority.from_level(priority_int),
        tags=json.loads(tags_json) if tags_json else [],
        scheduled_date=_parse_date(scheduled_str),
        deadline_date=_parse_date(deadline_str),
        created_at=_parse_datetime(created_str),
        updated_at=_parse_datetime(updated_str),
        completed_at=_parse_datetime(completed_str),
        archived=bool(archived_int),
        archived_at=_parse_datetime(archived_str),
        recurrence_rule=recurrence,
        parent_id=parent_id,
        notes=notes,
    )


def _task_to_row(task: Task) -> tuple:
    """Convert a Task dataclass to a database row tuple."""
    return (
        task.id,
        task.raw_md,
        task.title,
        task.status.value,
        task.priority.value,
        json.dumps(task.tags, ensure_ascii=False),
        task.scheduled_date.isoformat() if task.scheduled_date else None,
        task.deadline_date.isoformat() if task.deadline_date else None,
        task.created_at.isoformat() if task.created_at else None,
        task.updated_at.isoformat() if task.updated_at else None,
        task.completed_at.isoformat() if task.completed_at else None,
        int(task.archived),
        task.archived_at.isoformat() if task.archived_at else None,
        task.recurrence_rule,
        task.parent_id,
        task.notes,
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
        """Open (or create) the database and initialize schema."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)
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
        row = _task_to_row(task)
        set_clause = ", ".join(f"{col}=?" for col in _TASK_COLUMNS)
        sql = f"UPDATE tasks SET {set_clause} WHERE id=?"
        self.conn.execute(sql, row + (task.id,))
        self._update_fts(task)
        self.conn.commit()
        return task

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

        # Priority filter
        if filter_.priorities is not None:
            pri_values = [p.value for p in filter_.priorities]
            placeholders = ", ".join("?" for _ in pri_values)
            where_clauses.append(f"priority IN ({placeholders})")
            params.extend(pri_values)

        if filter_.min_priority is not None:
            where_clauses.append("priority >= ?")
            params.append(filter_.min_priority.value)

        # Tag filter (each tag must be present)
        if filter_.tags:
            for tag in filter_.tags:
                where_clauses.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

        # Date range filter
        if filter_.date_from:
            where_clauses.append("(deadline_date >= ? OR scheduled_date >= ?)")
            params.extend([filter_.date_from.isoformat(), filter_.date_from.isoformat()])
        if filter_.date_to:
            where_clauses.append("(deadline_date <= ? OR scheduled_date <= ?)")
            params.extend([filter_.date_to.isoformat(), filter_.date_to.isoformat()])

        # Overdue only
        if filter_.overdue_only:
            today = date.today().isoformat()
            where_clauses.append("deadline_date < ? AND status != 'DONE' AND archived = 0")
            params.append(today)

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

    def get_heatmap_data(self, year: int) -> dict[date, int]:
        """Return a mapping of date -> task count for the heatmap."""
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        rows = self.conn.execute(
            """SELECT COALESCE(deadline_date, scheduled_date, created_at) as d, COUNT(*)
               FROM tasks
               WHERE d BETWEEN ? AND ? AND archived = 0
               GROUP BY d""",
            (start, end),
        ).fetchall()
        result: dict[date, int] = {}
        for row in rows:
            parsed = _parse_date(row[0])
            if parsed:
                result[parsed] = row[1]
        return result

    def get_status_counts(self) -> dict[TaskStatus, int]:
        """Return counts grouped by task status."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM tasks WHERE archived=0 GROUP BY status"
        ).fetchall()
        return {TaskStatus.from_string(r[0]): r[1] for r in rows}

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
    # Archive helpers (Phase 2)
    # ------------------------------------------------------------------

    def get_tasks_for_archive(self, cutoff_date: date) -> list[Task]:
        cols = ", ".join(_TASK_COLUMNS)
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
            "priority": "priority",
            "title": "title",
            "scheduled": "scheduled_date",
        }
        clauses: list[str] = []
        for sc in sort_by:
            col = _field_map.get(sc.field, sc.field)
            direction = "ASC" if sc.ascending else "DESC"
            clauses.append(f"{col} {direction}")
        return clauses
