"""Application-wide signal bus for decoupled inter-module communication."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QObject, Signal

from ..models.task import Task
from ..models.task_status import TaskStatus


class SignalBus(QObject):
    """Singleton signal bus. Connect / emit Qt signals across modules."""

    # Scanning / data
    scan_completed = Signal(int)  # task_count
    scan_error = Signal(str)  # error message

    # Task CRUD
    task_created = Signal(Task)
    task_updated = Signal(Task)
    task_deleted = Signal(str)  # task_id
    task_status_changed = Signal(Task, TaskStatus)  # task, old_status

    # Reminders (Phase 2)
    reminder_fired = Signal(Task, int)  # task, interval_minutes

    # Archive (Phase 2)
    archive_completed = Signal(int)  # count

    # Heatmap
    date_selected = Signal(date)

    # Config
    config_changed = Signal()

    # App lifecycle
    application_quit = Signal()


_signal_bus_instance: SignalBus | None = None


def get_signal_bus() -> SignalBus:
    """Return the application-wide SignalBus singleton."""
    global _signal_bus_instance
    if _signal_bus_instance is None:
        _signal_bus_instance = SignalBus()
    return _signal_bus_instance
