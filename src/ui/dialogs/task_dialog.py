"""Task editor — Markdown-first: edit raw_md directly with live parsed preview."""

from __future__ import annotations

import uuid
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ...utils.signal_bus import get_signal_bus


class TaskDialog(QDialog):
    """Markdown-first task editor — one text input for raw_md with live preview."""

    def __init__(
        self,
        repository: TaskRepository,
        task: Task | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._task = task
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()
        self._signal_bus = get_signal_bus()
        self._editing = task is not None

        self.setWindowTitle("编辑任务" if self._editing else "新建任务")
        self.setObjectName("taskDialog")
        self.resize(520, 280)
        self.setMinimumSize(420, 220)

        self._build_ui()
        if self._editing and self._task:
            self._md_edit.setText(self._task.raw_md)
            self._notes_edit.setText(self._task.notes or "")
            if self._task.recurrence_rule:
                self._recurrence_edit.setText(self._task.recurrence_rule)
        self._update_preview()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # Markdown input
        root.addWidget(QLabel("Markdown 任务："))
        hint = QLabel(
            '格式：<tt>- [ ] TODO &lt;2026-05-20&gt; 任务标题 #标签</tt>'
        )
        hint.setObjectName("formatHint")
        root.addWidget(hint)

        self._md_edit = QLineEdit()
        self._md_edit.setObjectName("mdEdit")
        self._md_edit.setPlaceholderText("- [ ] TODO <2026-05-20> 任务标题 #标签")
        self._md_edit.textChanged.connect(self._update_preview)
        root.addWidget(self._md_edit)

        # Live preview
        root.addWidget(QLabel("解析预览："))
        self._preview = QLineEdit()
        self._preview.setReadOnly(True)
        self._preview.setObjectName("mdPreview")
        root.addWidget(self._preview)

        # Recurrence (optional)
        self._recurrence_edit = QLineEdit()
        self._recurrence_edit.setPlaceholderText("循环规则（如 +1d、+1w、+1m、+1y，可选）")
        root.addWidget(self._recurrence_edit)

        # Notes (optional)
        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(50)
        self._notes_edit.setPlaceholderText("备注（可选）...")
        root.addWidget(self._notes_edit)

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
        text = self._md_edit.text().strip()
        if not text:
            self._preview.setText("(空)")
            return
        try:
            parsed = self._parser.parse(text)
            parts = [
                f"状态={parsed.status.display_name}",
            ]
            if parsed.scheduled_date:
                parts.append(f"计划={parsed.scheduled_date.isoformat()}")
            if parsed.deadline_date:
                parts.append(f"截止={parsed.deadline_date.isoformat()}")
            parts.append(f"标题=\"{parsed.clean_title}\"")
            if parsed.tags:
                parts.append(f"标签={parsed.tags}")
            self._preview.setText(" | ".join(parts))
        except ValueError:
            self._preview.setText("⚠ 解析失败，请检查格式")

    def _on_accept(self) -> None:
        text = self._md_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "输入错误", "Markdown 任务不能为空。")
            return

        try:
            parsed = self._parser.parse(text)
        except ValueError:
            QMessageBox.warning(
                self,
                "解析失败",
                "无法解析 Markdown 格式。\n\n"
                "正确格式示例：\n"
                "- [ ] TODO <2026-05-20> 标题 #标签",
            )
            return

        notes = self._notes_edit.toPlainText().strip() or None
        recurrence = self._recurrence_edit.text().strip() or None

        if self._editing and self._task:
            self._task.raw_md = text
            self._task.title = parsed.clean_title
            self._task.status = parsed.status
            self._task.tags = parsed.tags
            self._task.scheduled_date = parsed.scheduled_date
            self._task.deadline_date = parsed.deadline_date
            self._task.notes = notes
            self._task.recurrence_rule = recurrence
            self._task.updated_at = datetime.now()
            self._repository.update(self._task)
            self._signal_bus.task_updated.emit(self._task)
        else:
            now = datetime.now()
            task = Task(
                id=str(uuid.uuid4()),
                raw_md=text,
                title=parsed.clean_title,
                status=parsed.status,
                tags=parsed.tags,
                scheduled_date=parsed.scheduled_date,
                deadline_date=parsed.deadline_date,
                notes=notes,
                recurrence_rule=recurrence,
                created_at=now,
                updated_at=now,
                activity_log=[{
                    "ts": now.isoformat(),
                    "content": "创建任务",
                    "status": parsed.status.value,
                    "progress": 0,
                }],
            )
            self._repository.insert(task)
            self._signal_bus.task_created.emit(task)

        self.accept()
