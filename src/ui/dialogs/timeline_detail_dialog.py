"""Timeline detail dialog with copy-MD and tag editing support."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...services.md_formatter import MarkdownTaskFormatter
from ...utils.signal_bus import get_signal_bus


def _fmt_ts(ts, short: bool = False) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return ts[:16]
    if short:
        return ts.strftime("%m-%d %H:%M")
    return ts.strftime("%Y-%m-%d %H:%M")


class TimelineDetailDialog(QDialog):
    """Shows activity timeline for a task, with Copy MD and tag editing."""

    def __init__(self, task: Task, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = task
        self._repository = repository
        self._formatter = MarkdownTaskFormatter()

        self.setWindowTitle(f"详情 — {task.title}")
        self.setObjectName("timelineDetailDialog")
        self.resize(500, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Task info header
        info = QLabel(f"<b>{task.title}</b>")
        info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info)

        status_label = QLabel(
            f"状态: {task.status.display_name}  |  "
            f"创建: {task.created_at.strftime('%Y-%m-%d %H:%M') if task.created_at else '—'}"
        )
        status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(status_label)

        # Tag editing row
        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)
        tag_row.addWidget(QLabel("标签："))
        tags_text = " ".join(f"#{t}" for t in task.tags)
        self._tag_edit = QLineEdit()
        self._tag_edit.setText(tags_text)
        self._tag_edit.setPlaceholderText("#标签1 #标签2 ...")
        self._tag_edit.setStyleSheet(
            "QLineEdit { font-family: Consolas, monospace; font-size: 12px; }"
        )
        tag_row.addWidget(self._tag_edit, 1)
        save_tags_btn = QPushButton("保存标签")
        save_tags_btn.setObjectName("saveBtn")
        save_tags_btn.clicked.connect(self._on_save_tags)
        tag_row.addWidget(save_tags_btn)
        layout.addLayout(tag_row)

        # Scrollable timeline entries
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #e0ddd6; border-radius: 6px; background: #fafaf8; }"
        )
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(4)

        entries: list[tuple[str, str, str]] = []
        entries.append(("▶", task.status.display_color, f"当前: {task.status.display_name}"))
        if task.completed_at:
            entries.append(("●", "#27ae60", "任务完成 ✓"))
        for e in reversed(task.activity_log):
            entries.append(("●", "#f39c12", e.get("content", "")))
        entries.append(
            ("○", "#aaa",
             f"创建任务 ({_fmt_ts(task.created_at.isoformat() if task.created_at else '', True)})")
        )

        for icon, color, content in entries:
            row = QHBoxLayout()
            row.setSpacing(6)
            dot = QLabel(f'<span style="color:{color};font-weight:bold;">{icon}</span>')
            dot.setFixedWidth(16)
            dot.setTextFormat(Qt.TextFormat.RichText)
            row.addWidget(dot)
            text = QLabel(content)
            text.setWordWrap(True)
            text.setStyleSheet("color: #444; font-size: 11px;")
            row.addWidget(text, 1)
            cl.addLayout(row)

        cl.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("复制 MD")
        copy_btn.setObjectName("saveBtn")
        copy_btn.clicked.connect(self._on_copy_md)
        btn_row.addWidget(copy_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_save_tags(self) -> None:
        """Parse tags from #tag1 #tag2 format and save to task."""
        import re
        text = self._tag_edit.text().strip()
        tags = re.findall(r"#([\w一-鿿/\-]+)", text)
        self._task.tags = tags
        # Regenerate raw_md with new tags
        self._task.raw_md = self._formatter.format(self._task)
        self._task.updated_at = datetime.now()
        self._repository.update(self._task)
        get_signal_bus().task_updated.emit(self._task)
        QMessageBox.information(self, "保存成功", f"标签已更新：{' '.join(f'#{t}' for t in tags)}")

    def _on_copy_md(self) -> None:
        task = self._task
        lines: list[str] = [f"## 活动时间线 — {task.title}", ""]
        if task.created_at:
            lines.append(f"- {task.created_at.strftime('%Y-%m-%d %H:%M')} 创建任务")
        for e in task.activity_log:
            ts = e.get("ts", "")
            try:
                dt_ts = datetime.fromisoformat(ts) if ts else None
                ts_str = dt_ts.strftime("%Y-%m-%d %H:%M") if dt_ts else ts
            except (ValueError, TypeError):
                ts_str = ts[:16] if ts else "—"
            lines.append(f"- {ts_str} {e.get('content', '')}")
        if task.completed_at:
            lines.append(f"- {task.completed_at.strftime('%Y-%m-%d %H:%M')} 任务完成 ✓")
        QApplication.clipboard().setText("\n".join(lines))
