"""Database schema migrations driven by SQLite PRAGMA user_version."""

from __future__ import annotations

import sqlite3
import uuid as _uuid
from datetime import date, datetime
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

MIGRATIONS: list[tuple[int, int, MigrationStep]] = [
    (0, 1, _migrate_0_to_1),
]
