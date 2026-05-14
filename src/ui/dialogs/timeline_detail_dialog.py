"""Read-only timeline detail dialog with copy-MD support."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...models.task import Task


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
    """Shows a read-only activity timeline for a task, with a Copy MD button."""

    def __init__(self, task: Task, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = task

        self.setWindowTitle(f"活动时间线 — {task.title}")
        self.setObjectName("timelineDetailDialog")
        self.resize(500, 480)

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

        # Scrollable timeline entries
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #e0ddd6; border-radius: 6px; background: #fafaf8; }")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(4)

        # Build entries (newest first)
        entries: list[tuple[str, str, str]] = []
        entries.append(("▶", task.status.display_color, f"当前: {task.status.display_name}"))
        if task.completed_at:
            entries.append(("●", "#27ae60", "任务完成 ✓"))
        for e in reversed(task.activity_log):
            entries.append(("●", "#f39c12", e.get("content", "")))
        entries.append(("○", "#aaa", f"创建任务 ({_fmt_ts(task.created_at.isoformat() if task.created_at else '', True)})"))

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
