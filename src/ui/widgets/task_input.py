"""Single-line Markdown task input widget."""

from __future__ import annotations

import uuid
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from ...models.repository import TaskRepository
from ...models.task import Task
from ...services.md_parser import MarkdownTaskParser
from ...utils.signal_bus import get_signal_bus


class TaskInputWidget(QWidget):
    """A QLineEdit that creates a Task when Enter is pressed."""

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._parser = MarkdownTaskParser()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setObjectName("taskInput")
        self._input.setPlaceholderText("输入任务 Markdown（Enter 创建）")
        self._input.returnPressed.connect(self._on_text_entered)
        layout.addWidget(self._input)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_text_entered(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        try:
            parsed = self._parser.parse(text)
        except ValueError:
            self._flash_error()
            return

        task = Task(
            id=str(uuid.uuid4()),
            raw_md=text,
            title=parsed.title if parsed.title else text,
            status=parsed.status,
            priority=parsed.priority,
            tags=parsed.tags,
            scheduled_date=parsed.scheduled_date,
            deadline_date=parsed.deadline_date,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._repository.insert(task)
        self._signal_bus.task_created.emit(task)
        self._input.clear()

    def _flash_error(self) -> None:
        self._input.setStyleSheet(
            "QLineEdit { border: 1px solid #e74c3c; background: #fdf0ef; }"
        )
        # Reset after brief delay
        from PySide6.QtCore import QTimer

        QTimer.singleShot(800, lambda: self._input.setStyleSheet(""))
