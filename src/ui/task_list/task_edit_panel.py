"""Inline task editor panel — raw_md QTextEdit with live preview and Save/Delete."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ...utils.signal_bus import get_signal_bus


class TaskEditPanel(QWidget):
    """Right-side panel for editing a task's raw_md with live preview."""

    task_saved = Signal(Task)
    task_deleted = Signal(str)  # task_id

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()
        self._signal_bus = get_signal_bus()
        self._current_task: Task | None = None

        self.setObjectName("taskEditPanel")
        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QLabel("编辑任务")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header)

        # Markdown editor
        md_label = QLabel("Markdown：")
        layout.addWidget(md_label)

        self._md_edit = QTextEdit()
        self._md_edit.setObjectName("mdEditor")
        self._md_edit.setPlaceholderText("- [ ] TODO [#A] <2026-05-20> 标题 #标签")
        self._md_edit.setStyleSheet(
            "QTextEdit { font-family: 'Consolas', 'Courier New', monospace;"
            " font-size: 12px; }"
        )
        self._md_edit.setMaximumHeight(80)
        self._md_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._md_edit)

        # Live preview
        preview_label = QLabel("预览：")
        layout.addWidget(preview_label)
        self._preview = QLabel("(选择任务进行编辑)")
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet(
            "QLabel { color: #555; background: #f8f8f8; padding: 6px;"
            " border-radius: 4px; font-size: 11px; }"
        )
        self._preview.setMinimumHeight(50)
        layout.addWidget(self._preview)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._save_btn = QPushButton("保存")
        self._save_btn.setObjectName("saveBtn")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)

        self._delete_btn = QPushButton("删除")
        self._delete_btn.setObjectName("deleteBtn")
        self._delete_btn.clicked.connect(self._on_delete)
        self._delete_btn.setEnabled(False)

        self._copy_btn = QPushButton("复制 MD")
        self._copy_btn.clicked.connect(self._on_copy)

        btn_layout.addWidget(self._save_btn)
        btn_layout.addWidget(self._delete_btn)
        btn_layout.addWidget(self._copy_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_task(self, task: Task) -> None:
        """Load a task into the editor."""
        self._current_task = task
        self._md_edit.blockSignals(True)
        self._md_edit.setText(task.raw_md)
        self._md_edit.blockSignals(False)
        self._save_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)
        self._update_preview()

    def clear(self) -> None:
        """Clear the editor."""
        self._current_task = None
        self._md_edit.blockSignals(True)
        self._md_edit.clear()
        self._md_edit.blockSignals(False)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._preview.setText("(选择任务进行编辑)")

    def current_task(self) -> Task | None:
        return self._current_task

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_text_changed(self) -> None:
        self._update_preview()

    def _update_preview(self) -> None:
        text = self._md_edit.toPlainText().strip()
        if not text:
            self._preview.setText("(空)")
            return
        try:
            parsed = self._parser.parse(text)
            parts = [
                f"状态={parsed.status.display_name}",
                f"优先级={parsed.priority.display_tag or '无'}",
            ]
            if parsed.scheduled_date:
                parts.append(f"计划={parsed.scheduled_date.isoformat()}")
            if parsed.deadline_date:
                parts.append(f"截止={parsed.deadline_date.isoformat()}")
            parts.append(f'标题="{parsed.clean_title}"')
            if parsed.tags:
                parts.append(f"标签={parsed.tags}")
            self._preview.setText("  |  ".join(parts))
        except ValueError:
            self._preview.setText("⚠ 无法解析 — 请检查 Markdown 格式")

    def _on_save(self) -> None:
        if not self._current_task:
            return
        text = self._md_edit.toPlainText().strip()
        if not text:
            return

        try:
            parsed = self._parser.parse(text)
        except ValueError:
            QMessageBox.warning(self, "解析失败", "Markdown 格式不正确，请检查。")
            return

        task = self._current_task
        old_status = task.status
        task.raw_md = text
        task.title = parsed.clean_title
        task.status = parsed.status
        task.priority = parsed.priority
        task.tags = parsed.tags
        task.scheduled_date = parsed.scheduled_date
        task.deadline_date = parsed.deadline_date
        task.updated_at = datetime.now()
        if task.status == TaskStatus.DONE and old_status != TaskStatus.DONE:
            task.completed_at = datetime.now()

        self._repository.update(task)
        if task.status != old_status:
            self._signal_bus.task_status_changed.emit(task, old_status)
        else:
            self._signal_bus.task_updated.emit(task)

    def _on_delete(self) -> None:
        if not self._current_task:
            return
        task = self._current_task
        result = QMessageBox.question(
            self,
            "确认删除",
            f'确定要删除 "{task.title}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._repository.delete(task.id)
            self._signal_bus.task_deleted.emit(task.id)
            self.clear()

    def _on_copy(self) -> None:
        if self._current_task:
            QApplication.clipboard().setText(self._current_task.raw_md)
