"""Single-line Markdown task input widget."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from ...models.task import Task
from ...services.task_service import TaskService


class TaskInputWidget(QWidget):
    """A QLineEdit that creates a Task when Enter is pressed."""

    def __init__(self, task_service: TaskService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task_service = task_service

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
            self._task_service.create_task(text)
        except ValueError:
            self._flash_error()
            return

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
        QTimer.singleShot(800, lambda: self._input.setStyleSheet(""))
