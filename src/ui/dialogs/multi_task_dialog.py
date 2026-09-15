"""MultiTaskDialog —— 批量新建任务（多行 Markdown，一行一个任务）。

每行按标准 Markdown 任务语法解析，一次性批量写入；``create_tasks_bulk``
只发一次 ``tasks_bulk_created`` 信号，避免逐条插入导致列表反复刷新。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.task_service import TaskService

__all__ = ["MultiTaskDialog"]


class MultiTaskDialog(QDialog):
    """多行 Markdown 批量创建。

    Signals:
        tasks_created(count): 成功创建的任务数量。
    """

    tasks_created = Signal(int)

    def __init__(
        self,
        task_service: TaskService,
        partition_id: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("批量新建任务")
        self.resize(580, 430)
        self._svc = task_service
        self._partition_id = partition_id or None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        hint = QLabel(
            "每行一个任务，支持完整 Markdown 语法：\n"
            "- [ ] 修复登录 <2026-09-20> #前端"
        )
        hint.setStyleSheet("font-size: 12px;")
        layout.addWidget(hint)

        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText(
            "- [ ] 任务一 <2026-09-20> #标签\n- [ ] 任务二 #标签"
        )
        layout.addWidget(self._edit, 1)

        self._error = QLabel("")
        self._error.setStyleSheet("font-size: 11.5px;")
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        lines = [
            ln.strip() for ln in self._edit.toPlainText().splitlines() if ln.strip()
        ]
        if not lines:
            self._error.setText("请输入至少一行任务。")
            return

        now = datetime.now()
        created: list[Task] = []
        errors: list[str] = []
        for idx, line in enumerate(lines, 1):
            try:
                parsed = self._svc.parse_markdown(line)
            except ValueError:
                errors.append(f"第 {idx} 行格式不正确")
                continue
            created.append(
                Task(
                    id=str(uuid.uuid4()),
                    raw_md=line,
                    title=parsed.clean_title,
                    status=parsed.status,
                    tags=parsed.tags,
                    urgency=parsed.urgency,
                    scheduled_date=parsed.scheduled_date,
                    deadline_date=parsed.deadline_date,
                    deadline_time=parsed.deadline_time,
                    partition_id=self._partition_id,
                    created_at=now,
                    updated_at=now,
                    progress=100 if parsed.status == TaskStatus.DONE else 0,
                )
            )

        if not created:
            self._error.setText("；".join(errors) or "没有可创建的任务。")
            return

        self._svc.create_tasks_bulk(created)
        self.tasks_created.emit(len(created))
        self.accept()
