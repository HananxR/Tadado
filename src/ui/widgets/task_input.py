"""Single-line Markdown task input widget."""

from __future__ import annotations

import uuid
from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from ...models.repository import TaskRepository
from ...models.task import Task
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ...utils.signal_bus import get_signal_bus


class TaskInputWidget(QWidget):
    """A QLineEdit that creates a Task when Enter is pressed."""

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setObjectName("taskInput")
        self._input.setPlaceholderText("- [ ] TODO <2026-05-20> 输入Markdown任务，Enter创建  |  Ctrl+N 聚焦")
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

        now = datetime.now()
        task = Task(
            id=str(uuid.uuid4()),
            raw_md=text,
            title=parsed.clean_title,
            status=parsed.status,
            tags=parsed.tags,
            scheduled_date=parsed.scheduled_date,
            deadline_date=parsed.deadline_date,
            created_at=now,
            updated_at=now,
            activity_log=[{
                "ts": now.isoformat(),
                "content": "创建任务",
                "status": parsed.status.value,
                "progress": 0,
            }],
        )
        # Normalize raw_md through the formatter
        task.raw_md = self._formatter.format(task)
        self._repository.insert(task)
        self._signal_bus.task_created.emit(task)
        self._input.clear()

    def focus_input(self) -> None:
        """Focus and select all text in the input field."""
        self._input.setFocus()
        self._input.selectAll()

    def _flash_error(self) -> None:
        from ...utils.design_tokens import get_tokens
        t = get_tokens()
        self._input.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {t.danger}; background: {t.danger_bg}; }}"
        )
        from PySide6.QtCore import QTimer

        QTimer.singleShot(800, lambda: self._input.setStyleSheet(""))
