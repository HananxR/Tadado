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
    QVBoxLayout,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...services.md_formatter import MarkdownTaskFormatter
from ...utils.design_tokens import get_tokens
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
        status_label.setStyleSheet("font-size: 11px;")
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

        # Timeline text block (matching edit panel style)
        from PySide6.QtWidgets import QTextBrowser
        timeline = QTextBrowser()
        timeline.setReadOnly(True)
        timeline.setStyleSheet(
            "QTextBrowser { font-size: 12px; padding: 6px; }"
        )

        t = get_tokens()
        def _row(icon: str, color: str, ts: str, content: str) -> str:
            return (
                f'<p style="margin:3px 0;font-family:Consolas,monospace;font-size:12px;">'
                f'<span style="color:{color};font-weight:bold;">{icon}</span>'
                f' <span style="color:{color};">{ts:>11}</span>'
                f' <span style="color:{t.text_primary};">{content}</span>'
                f'</p>'
            )

        rows: list[str] = []
        sc = task.status.display_color
        # Urgency label
        urgency = getattr(task, 'urgency', 3)
        _URGENCY_NAMES = {0: "紧急", 1: "重要", 2: "关注", 3: "普通"}
        _URGENCY_COLORS = {0: t.urgency_urgent, 1: t.urgency_high, 2: t.urgency_medium, 3: t.text_secondary}
        urgency_label = _URGENCY_NAMES.get(urgency, "普通")
        urgency_color = _URGENCY_COLORS.get(urgency, t.text_secondary)
        rows.append(_row("▶", sc, _fmt_ts(datetime.now().isoformat(), True),
                          f"当前: {task.status.display_name}  |  优先级: "
                          f'<span style="color:{urgency_color};font-weight:bold;">{urgency_label}</span>'))
        if task.completed_at:
            rows.append(_row("●", t.timeline_done, _fmt_ts(task.completed_at.isoformat(), True),
                              "任务完成 ✓"))
        for e in reversed(task.activity_log[:10]):
            ts = _fmt_ts(e.get("ts", ""), True)
            rows.append(_row("●", t.timeline_dot, ts, e.get("content", "")))

        timeline.setHtml(f'<div>{"".join(rows)}</div>')
        layout.addWidget(timeline, 1)

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
