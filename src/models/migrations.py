"""Database schema migrations driven by SQLite PRAGMA user_version."""

from __future__ import annotations

import json as _json
import sqlite3
import uuid as _uuid
from datetime import date, datetime, timedelta
from typing import Callable, Union

# A migration step can be a raw SQL string or a callable that receives the connection.
MigrationStep = Union[str, Callable[[sqlite3.Connection], None]]


def migrate(conn: sqlite3.Connection) -> int:
    """Run pending migrations and return the final schema version."""
    current_version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    for from_ver, to_ver, step in MIGRATIONS:
        if current_version == from_ver:
            if callable(step):
                step(conn)
            else:
                conn.executescript(step)
            conn.execute(f"PRAGMA user_version = {to_ver}")
            current_version = to_ver
    return current_version


# ------------------------------------------------------------------
# Migration 0 → 1: Full initial schema
# ------------------------------------------------------------------

def _migrate_0_to_1(conn: sqlite3.Connection) -> None:
    """Create all tables with current columns, indexes, seed data, and fix legacy status."""

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            raw_md TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'TODO',
            priority INTEGER NOT NULL DEFAULT 0,
            tags TEXT DEFAULT '[]',
            scheduled_date TEXT,
            deadline_date TEXT,
            deadline_time TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            archived INTEGER NOT NULL DEFAULT 0,
            archived_at TEXT,
            recurrence_rule TEXT,
            parent_id TEXT,
            partition_id TEXT,
            notes TEXT DEFAULT '',
            activity_log TEXT DEFAULT '[]',
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

        CREATE TABLE IF NOT EXISTS partitions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            password TEXT DEFAULT '',
            archive_days INTEGER NOT NULL DEFAULT 9999,
            created_at TEXT NOT NULL
        );
    """)

    for col_stmt in _ALTER_COLUMNS:
        try:
            conn.execute(col_stmt)
        except sqlite3.OperationalError:
            pass

    conn.execute(
        "UPDATE tasks SET status = 'TODO' WHERE status IN ('WAIT', 'LATER', 'URGENT')"
    )
    conn.execute(
        "UPDATE tasks SET status = 'OVERDUE' WHERE deadline_date < ? "
        "AND archived = 0 AND status NOT IN ('DONE', 'OVERDUE')",
        (date.today().isoformat(),),
    )

    cur = conn.execute("SELECT COUNT(*) FROM partitions")
    if cur.fetchone()[0] == 0:
        from .partition import DEFAULT_PARTITIONS

        now = datetime.now().isoformat()
        for i, name in enumerate(DEFAULT_PARTITIONS):
            conn.execute(
                "INSERT INTO partitions (id, name, sort_order, created_at) VALUES (?, ?, ?, ?)",
                (str(_uuid.uuid4()), name, i, now),
            )

    work_row = conn.execute(
        "SELECT id FROM partitions ORDER BY sort_order LIMIT 1"
    ).fetchone()
    if work_row:
        conn.execute(
            "UPDATE tasks SET partition_id = ? WHERE partition_id IS NULL",
            (work_row[0],),
        )


_ALTER_COLUMNS = [
    "ALTER TABLE tasks ADD COLUMN activity_log TEXT DEFAULT '[]'",
    "ALTER TABLE tasks ADD COLUMN deadline_time TEXT",
    "ALTER TABLE tasks ADD COLUMN partition_id TEXT REFERENCES partitions(id) ON DELETE SET NULL",
    "ALTER TABLE partitions ADD COLUMN password TEXT DEFAULT ''",
    "ALTER TABLE tasks ADD COLUMN progress INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE partitions ADD COLUMN archive_days INTEGER NOT NULL DEFAULT 9999",
    "ALTER TABLE tasks ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0",
]

# ------------------------------------------------------------------
# Migration registry
# ------------------------------------------------------------------

def compute_activity_counts(activity_log_json: str, today: date | None = None) -> tuple[int, int, int, int, int, int]:
    """Return (yesterday, today, week, month, last_week, last_month) counts from activity_log JSON."""
    if today is None:
        today = date.today()
    yesterday = today - timedelta(days=1)
    # 本周
    monday = today - timedelta(days=today.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    # 本月
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    # 上周
    last_monday = today - timedelta(days=today.isoweekday() + 6)
    last_sunday = last_monday + timedelta(days=6)
    # 上月
    first_of_this_month = today.replace(day=1)
    last_day_of_last_month = first_of_this_month - timedelta(days=1)
    first_of_last_month = last_day_of_last_month.replace(day=1)

    counts = [0, 0, 0, 0, 0, 0]
    try:
        entries = _json.loads(activity_log_json) if activity_log_json else []
    except (_json.JSONDecodeError, TypeError):
        entries = []
    for entry in entries:
        ts = entry.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts).date()
        except (ValueError, TypeError):
            continue
        if dt == yesterday:
            counts[0] += 1
        if dt == today:
            counts[1] += 1
        if monday <= dt <= sunday:
            counts[2] += 1
        if month_start <= dt <= month_end:
            counts[3] += 1
        if last_monday <= dt <= last_sunday:
            counts[4] += 1
        if first_of_last_month <= dt <= last_day_of_last_month:
            counts[5] += 1
    return tuple(counts)


def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    """Add activity count columns for progress bar sorting."""
    conn.executescript("""
        ALTER TABLE tasks ADD COLUMN activity_yesterday INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE tasks ADD COLUMN activity_today INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE tasks ADD COLUMN activity_week INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE tasks ADD COLUMN activity_month INTEGER NOT NULL DEFAULT 0;
    """)
    # Backfill existing rows from activity_log data
    rows = conn.execute("SELECT id, activity_log FROM tasks").fetchall()
    for row in rows:
        counts = compute_activity_counts(row[1])
        conn.execute(
            "UPDATE tasks SET activity_yesterday=?, activity_today=?, activity_week=?, activity_month=? WHERE id=?",
            (*counts, row[0]),
        )


def _migrate_2_to_3(conn: sqlite3.Connection) -> None:
    """Backfill activity count columns from existing activity_log data."""
    rows = conn.execute("SELECT id, activity_log FROM tasks").fetchall()
    for row in rows:
        counts = compute_activity_counts(row[1])
        conn.execute(
            "UPDATE tasks SET activity_yesterday=?, activity_today=?, activity_week=?, activity_month=? WHERE id=?",
            (*counts, row[0]),
        )


def _migrate_3_to_4(conn: sqlite3.Connection) -> None:
    """Add last_week and last_month activity count columns."""
    conn.executescript("""
        ALTER TABLE tasks ADD COLUMN activity_last_week INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE tasks ADD COLUMN activity_last_month INTEGER NOT NULL DEFAULT 0;
    """)
    rows = conn.execute("SELECT id, activity_log FROM tasks").fetchall()
    for row in rows:
        counts = compute_activity_counts(row[1])
        conn.execute(
            "UPDATE tasks SET activity_last_week=?, activity_last_month=? WHERE id=?",
            (counts[4], counts[5], row[0]),
        )


MIGRATIONS: list[tuple[int, int, MigrationStep]] = [
    (0, 1, _migrate_0_to_1),
    (1, 2, _migrate_1_to_2),
    (2, 3, _migrate_2_to_3),
    (3, 4, _migrate_3_to_4),
]
