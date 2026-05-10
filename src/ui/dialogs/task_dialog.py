"""Task creation / editing dialog with real-time Markdown preview."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...models.priority import Priority
from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.md_formatter import MarkdownTaskFormatter
from ...utils.signal_bus import get_signal_bus


class TaskDialog(QDialog):
    """Dialog for creating or editing a task."""

    def __init__(
        self,
        repository: TaskRepository,
        task: Task | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._task = task
        self._formatter = MarkdownTaskFormatter()
        self._signal_bus = get_signal_bus()
        self._editing = task is not None

        self.setWindowTitle("编辑任务" if self._editing else "新建任务")
        self.setObjectName("taskDialog")
        self.resize(480, 500)
        self.setMinimumSize(400, 400)

        self._build_ui()
        if self._editing:
            self._populate_from_task()
        self._update_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("任务标题")
        self._title_edit.textChanged.connect(self._update_preview)
        form.addRow("标题", self._title_edit)

        self._status_combo = QComboBox()
        for s in TaskStatus:
            self._status_combo.addItem(s.display_name, s)
        self._status_combo.currentIndexChanged.connect(self._update_preview)
        form.addRow("状态", self._status_combo)

        self._priority_combo = QComboBox()
        for p in Priority:
            self._priority_combo.addItem(p.display_tag if p != Priority.NONE else "无", p)
        self._priority_combo.currentIndexChanged.connect(self._update_preview)
        form.addRow("优先级", self._priority_combo)

        self._deadline_date = QDateEdit()
        self._deadline_date.setCalendarPopup(True)
        self._deadline_date.setDisplayFormat("yyyy-MM-dd")
        self._deadline_date.setSpecialValueText("无")
        self._deadline_date.setDate(self._deadline_date.minimumDate())
        self._deadline_date.dateChanged.connect(self._update_preview)
        form.addRow("截止日", self._deadline_date)

        self._scheduled_date = QDateEdit()
        self._scheduled_date.setCalendarPopup(True)
        self._scheduled_date.setDisplayFormat("yyyy-MM-dd")
        self._scheduled_date.setSpecialValueText("无")
        self._scheduled_date.setDate(self._scheduled_date.minimumDate())
        self._scheduled_date.dateChanged.connect(self._update_preview)
        form.addRow("计划日", self._scheduled_date)

        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("tag1 tag2")
        self._tags_edit.textChanged.connect(self._update_preview)
        form.addRow("标签", self._tags_edit)

        self._recurrence_edit = QLineEdit()
        self._recurrence_edit.setPlaceholderText('如：+1d、+1w、+1m、+1y')
        form.addRow("循环规则", self._recurrence_edit)

        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(80)
        self._notes_edit.setPlaceholderText("备注...")
        form.addRow("备注", self._notes_edit)

        root.addLayout(form)

        # Preview
        preview_label = QLabel("Markdown 预览：")
        root.addWidget(preview_label)
        self._preview = QLineEdit()
        self._preview.setReadOnly(True)
        self._preview.setStyleSheet(
            "QLineEdit { font-family: 'Consolas', 'Courier New', monospace; }"
        )
        root.addWidget(self._preview)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        status = self._status_combo.currentData() or TaskStatus.TODO
        priority = self._priority_combo.currentData() or Priority.NONE
        deadline = self._date_or_none(self._deadline_date)
        scheduled = self._date_or_none(self._scheduled_date)
        title = self._title_edit.text() or "(标题)"
        tags_str = self._tags_edit.text().strip()
        tags = [t.lstrip("#") for t in tags_str.split()] if tags_str else None
        raw_md = self._formatter.format_fields(
            status=status,
            priority=priority,
            scheduled_date=scheduled,
            deadline_date=deadline,
            title=title,
            tags=tags,
        )
        self._preview.setText(raw_md)

    def _on_accept(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "输入错误", "标题不能为空。")
            return

        status: TaskStatus = self._status_combo.currentData() or TaskStatus.TODO
        priority: Priority = self._priority_combo.currentData() or Priority.NONE
        deadline = self._date_or_none(self._deadline_date)
        scheduled = self._date_or_none(self._scheduled_date)
        tags_str = self._tags_edit.text().strip()
        tags = [t.lstrip("#") for t in tags_str.split()] if tags_str else []
        recurrence = self._recurrence_edit.text().strip() or None
        notes = self._notes_edit.toPlainText().strip() or None

        raw_md = self._formatter.format_fields(
            status=status,
            priority=priority,
            scheduled_date=scheduled,
            deadline_date=deadline,
            title=title,
            tags=tags,
        )

        if self._editing and self._task:
            self._task.title = title
            self._task.status = status
            self._task.priority = priority
            self._task.deadline_date = deadline
            self._task.scheduled_date = scheduled
            self._task.tags = tags
            self._task.raw_md = raw_md
            self._task.recurrence_rule = recurrence
            self._task.notes = notes
            self._task.updated_at = datetime.now()
            self._repository.update(self._task)
            self._signal_bus.task_updated.emit(self._task)
        else:
            task = Task(
                id=str(uuid.uuid4()),
                raw_md=raw_md,
                title=title,
                status=status,
                priority=priority,
                tags=tags,
                scheduled_date=scheduled,
                deadline_date=deadline,
                recurrence_rule=recurrence,
                notes=notes,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            self._repository.insert(task)
            self._signal_bus.task_created.emit(task)

        self.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _populate_from_task(self) -> None:
        if not self._task:
            return
        t = self._task
        self._title_edit.setText(t.title)

        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == t.status:
                self._status_combo.setCurrentIndex(i)
                break

        for i in range(self._priority_combo.count()):
            if self._priority_combo.itemData(i) == t.priority:
                self._priority_combo.setCurrentIndex(i)
                break

        if t.deadline_date:
            self._deadline_date.setDate(t.deadline_date)
        if t.scheduled_date:
            self._scheduled_date.setDate(t.scheduled_date)
        if t.tags:
            self._tags_edit.setText(" ".join(t.tags))
        if t.recurrence_rule:
            self._recurrence_edit.setText(t.recurrence_rule)
        if t.notes:
            self._notes_edit.setText(t.notes)

    @staticmethod
    def _date_or_none(edit: QDateEdit) -> date | None:
        d = edit.date()
        if d == edit.minimumDate():
            return None
        return date(d.year(), d.month(), d.day())
