"""Multi-task creation dialog — batch create tasks from multiple Markdown lines."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDateEdit,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
)

from ...config import AppConfig
from ...models.repository import TaskRepository
from ...models.task import Task
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ..widgets.deadline_calculator import DeadlineIntervalCalculator


class MultiTaskDialog(QDialog):
    """Modal dialog for creating multiple tasks at once."""

    tasks_created = Signal(int)

    def __init__(
        self,
        repository: TaskRepository,
        partition_id: str,
        config: AppConfig | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._partition_id = partition_id
        self._config = config
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()
        self._setup_ui()
        self.setWindowTitle("多任务创建")
        self.setMinimumSize(520, 420)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Multi-line markdown editor with pre-populated template
        layout.addWidget(QLabel("输入多个任务（每行一个 Markdown 任务）："))
        self._text_edit = QTextEdit()
        self._text_edit.setObjectName("multiTaskEditor")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._text_edit.setText(
            f"- [ ]  <{now_str}> 新任务1 #标签\n"
            f"- [ ]  <{now_str}> 新任务2 #标签\n"
            f"- [ ]  <{now_str}> 新任务3 #标签"
        )
        self._text_edit.setMinimumHeight(100)
        layout.addWidget(self._text_edit)

        # Deadline calculator (collapsible)
        self._calc_group = QGroupBox("截止区间计算器（可选）")
        self._calc_group.setCheckable(True)
        self._calc_group.setChecked(False)
        self._calc = DeadlineIntervalCalculator(parent=self)
        self._calc.deadline_suggested.connect(self._on_deadline_suggested)
        calc_layout = QVBoxLayout(self._calc_group)
        calc_layout.addWidget(self._calc)
        layout.addWidget(self._calc_group)

        # Shared date/time pickers
        picker_row = QHBoxLayout()
        picker_row.setSpacing(12)

        now = datetime.now()
        picker_row.addWidget(QLabel("创建时间:"))
        self._created_date = QDateEdit(QDate(now.year, now.month, now.day))
        self._created_date.setDisplayFormat("yyyy-MM-dd")
        self._created_date.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._created_date.setCalendarPopup(True)
        picker_row.addWidget(self._created_date)

        self._created_time = QTimeEdit(QTime(now.hour, now.minute))
        self._created_time.setDisplayFormat("HH:mm")
        self._created_time.setButtonSymbols(QAbstractSpinBox.NoButtons)
        picker_row.addWidget(self._created_time)

        picker_row.addSpacing(16)

        picker_row.addWidget(QLabel("截止时间:"))
        self._deadline_date = QDateEdit(QDate(now.year, now.month, now.day + 1))
        self._deadline_date.setDisplayFormat("yyyy-MM-dd")
        self._deadline_date.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._deadline_date.setCalendarPopup(True)
        picker_row.addWidget(self._deadline_date)

        self._deadline_time = QTimeEdit(QTime(23, 59))
        self._deadline_time.setDisplayFormat("HH:mm")
        self._deadline_time.setButtonSymbols(QAbstractSpinBox.NoButtons)
        picker_row.addWidget(self._deadline_time)

        picker_row.addStretch()
        layout.addLayout(picker_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._create_btn = QPushButton("创建 0 个任务")
        self._create_btn.setObjectName("saveBtn")
        self._create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(self._create_btn)

        layout.addLayout(btn_row)

    def _on_deadline_suggested(self, d: QDate, t: QTime) -> None:
        self._deadline_date.setDate(d)
        self._deadline_time.setTime(t)

    def _on_create(self) -> None:
        text = self._text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "无内容", "请输入至少一行任务。")
            return

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        created_dt = datetime(
            self._created_date.date().year(),
            self._created_date.date().month(),
            self._created_date.date().day(),
            self._created_time.time().hour(),
            self._created_time.time().minute(),
        )
        shared_deadline_date = self._deadline_date.date().toPython()
        shared_deadline_time = f"{self._deadline_time.time().hour():02d}:{self._deadline_time.time().minute():02d}"
        now_str = datetime.now().isoformat()

        tasks_to_insert: list[Task] = []
        errors: list[str] = []

        for i, line in enumerate(lines, 1):
            try:
                parsed = self._parser.parse(line)
            except ValueError as e:
                errors.append(f"第{i}行解析失败: {e}")
                continue

            if not parsed.tags:
                errors.append(f"第{i}行缺少标签（#标签），标签是必填项")
                continue

            # Apply shared deadline if the parsed line has none
            dl_date = parsed.deadline_date or shared_deadline_date
            dl_time = parsed.deadline_time or shared_deadline_time

            raw_md = self._formatter.format_fields(
                status=parsed.status,
                scheduled_date=parsed.scheduled_date,
                deadline_date=dl_date,
                deadline_time=dl_time,
                title=parsed.clean_title,
                tags=parsed.tags,
                urgency=parsed.urgency,
            )

            task = Task(
                id=str(uuid.uuid4()),
                raw_md=raw_md,
                title=parsed.clean_title,
                status=parsed.status,
                tags=parsed.tags,
                urgency=parsed.urgency,
                scheduled_date=parsed.scheduled_date,
                deadline_date=dl_date,
                deadline_time=dl_time,
                partition_id=self._partition_id,
                created_at=created_dt,
                activity_log=[{
                    "ts": now_str,
                    "content": "[批量创建] 创建任务",
                    "status": parsed.status.value,
                    "progress": 0,
                }],
            )
            tasks_to_insert.append(task)

        if errors:
            QMessageBox.warning(
                self,
                "部分任务创建失败",
                "\n".join(errors) + f"\n\n已创建 {len(tasks_to_insert)} 个任务。",
            )

        if tasks_to_insert:
            for task in tasks_to_insert:
                self._repository.insert(task)
            self.tasks_created.emit(len(tasks_to_insert))
            self.accept()
        elif errors:
            return
        else:
            QMessageBox.warning(self, "无有效任务", "没有可以创建的任务。")
