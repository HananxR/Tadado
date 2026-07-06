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
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ...services.task_service import TaskService


class TaskDialog(QDialog):
    """Markdown-first task editor — one text input for raw_md with live preview."""

    def __init__(
        self,
        repository: TaskRepository,
        task: Task | None = None,
        task_service: TaskService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._task_service = task_service
        self._task = task
        self._parser = task_service._parser if task_service else MarkdownTaskParser()
        self._formatter = task_service._formatter if task_service else MarkdownTaskFormatter()
        self._editing = task is not None

        self.setWindowTitle("编辑任务" if self._editing else "新建任务")
        self.setObjectName("taskDialog")
        self.resize(520, 300)
        self.setMinimumSize(420, 240)

        self._build_ui()
        if self._editing and self._task:
            self._md_edit.setText(self._task.raw_md)
            if self._task.created_at:
                self._created_label.setText(
                    f"创建: {self._task.created_at.strftime('%Y-%m-%d %H:%M')}"
                )
                self._created_label.setVisible(True)
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
            '格式：<tt>- [   ] &lt;2026-06-15 23:59&gt; 任务标题 #标签</tt>'
        )
        hint.setObjectName("formatHint")
        root.addWidget(hint)

        self._md_edit = QLineEdit()
        self._md_edit.setObjectName("mdEdit")
        self._md_edit.setPlaceholderText("- [   ] <2026-06-15 23:59> 任务标题 #标签")
        self._md_edit.textChanged.connect(self._update_preview)
        root.addWidget(self._md_edit)

        # Live preview
        root.addWidget(QLabel("解析预览："))
        self._preview = QLabel()
        self._preview.setWordWrap(True)
        self._preview.setObjectName("mdPreview")
        root.addWidget(self._preview)

        # Task metadata (edit mode only)
        self._created_label = QLabel()
        self._created_label.setObjectName("createdLabel")
        self._created_label.setVisible(False)
        root.addWidget(self._created_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
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
            _urgency_labels = {0: "紧急", 1: "重要", 2: "关注", 3: "普通"}
            parts = [
                f"优先级={_urgency_labels.get(parsed.urgency, '?')}",
            ]
            if parsed.scheduled_date:
                parts.append(f"计划={parsed.scheduled_date.isoformat()}")
            if parsed.deadline_date:
                dl = parsed.deadline_date.isoformat()
                if parsed.deadline_time:
                    dl += f" {parsed.deadline_time}"
                parts.append(f"截止={dl}")
            parts.append(f'标题="{parsed.clean_title}"')
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
                "- [   ] <2026-06-15 23:59> 标题 #标签",
            )
            return

        if self._editing and self._task:
            old_status = self._task.status
            # Only update status from parsed text if a status keyword is
            # explicitly present; otherwise preserve the existing status
            # (the canonical format omits status keywords).
            _has_status_kw = any(
                kw in text.upper() for kw in ("TODO", "DOING", "DONE", "OVERDUE")
            )
            if _has_status_kw:
                self._task.status = parsed.status
            self._task.title = parsed.clean_title
            self._task.tags = parsed.tags
            self._task.scheduled_date = parsed.scheduled_date
            self._task.deadline_date = parsed.deadline_date
            self._task.deadline_time = parsed.deadline_time
            self._task.urgency = parsed.urgency
            self._task.updated_at = datetime.now()
            if self._task.status == TaskStatus.DONE:
                self._task.progress = 100
                self._task.completed_at = self._task.deadline_date or datetime.now()
            # Validate: created_at must not be after deadline
            if self._task.created_at and self._task.deadline_date:
                # Build full deadline datetime for precise comparison
                if self._task.deadline_time:
                    try:
                        t = datetime.strptime(self._task.deadline_time, "%H:%M").time()
                        dl_dt = datetime.combine(self._task.deadline_date, t)
                    except (ValueError, TypeError):
                        dl_dt = datetime.combine(self._task.deadline_date, datetime.max.time())
                else:
                    dl_dt = datetime.combine(self._task.deadline_date, datetime.max.time())
                if self._task.created_at > dl_dt:
                    dl_str = dl_dt.strftime("%Y-%m-%d %H:%M")
                    QMessageBox.warning(
                        self, "时间校验失败",
                        f"创建时间({self._task.created_at.strftime('%Y-%m-%d %H:%M')})"
                        f"不能晚于截止时间({dl_str})，请调整后再保存。"
                    )
                    return
            # Normalize to canonical Markdown (mirrors TaskEditPanel._on_save)
            self._task.raw_md = self._formatter.format(self._task)
            if self._task_service:
                if self._task.status != old_status:
                    self._task_service.change_task_status(self._task, self._task.status)
                else:
                    self._task_service.update_task(self._task)
            else:
                self._repository.update(self._task)
                if self._task.status != old_status:
                    from ...utils.signal_bus import get_signal_bus
                    get_signal_bus().task_status_changed.emit(self._task, old_status)
                else:
                    from ...utils.signal_bus import get_signal_bus
                    get_signal_bus().task_updated.emit(self._task)
        else:
            now = datetime.now()
            task = Task(
                id=str(uuid.uuid4()),
                raw_md=text,  # temporary; normalized below
                title=parsed.clean_title,
                status=parsed.status,
                tags=parsed.tags,
                scheduled_date=parsed.scheduled_date,
                deadline_date=parsed.deadline_date,
                deadline_time=parsed.deadline_time,
                urgency=parsed.urgency,
                created_at=now,
                updated_at=now,
                activity_log=[{
                    "ts": now.isoformat(),
                    "content": "创建任务",
                    "status": parsed.status.value,
                    "progress": 100 if parsed.status == TaskStatus.DONE else 0,
                }],
            )
            # Normalize to canonical Markdown
            task.raw_md = self._formatter.format(task)
            if self._task_service:
                self._task_service._repo.insert(task)
                self._task_service._bus.task_created.emit(task)
            else:
                self._repository.insert(task)
                from ...utils.signal_bus import get_signal_bus
                get_signal_bus().task_created.emit(task)
            self._signal_bus.task_created.emit(task)

        self.accept()
