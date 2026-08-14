"""Read-only activity timeline view — same display style as the main editor's.

Shared by dialogs (e.g. TaskDialog) so task activity looks identical to the
main editor's 活动时间线; deliberately has no click-to-edit behavior.
"""

from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTextBrowser

from ...models.task import Task
from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens

_URGENCY_NAMES = {0: "紧急", 1: "重要", 2: "关注", 3: "普通"}


def _fmt_ts(ts, short: bool = False) -> str:
    """Format ISO timestamp — mirrors task_edit_panel._fmt_ts."""
    if ts is None:
        return "—"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return ts[:16]
    if short:
        return ts.strftime("%m-%d %H:%M:%S")
    return ts.strftime("%Y-%m-%d %H:%M:%S")


class TimelineView(QTextBrowser):
    """只读活动时间线（新→旧），与主界面时间线样式一致；无活动记录时留空."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setMinimumHeight(120)
        # 上限内随内容伸展；超出上限启用内部滚动条，避免撑爆窗口裁掉内容
        self.setMaximumHeight(320)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("QTextBrowser { font-size: 12px; padding: 4px; }")

    def set_task(self, task: Task | None) -> None:
        """Render the task's activity log; empty log renders nothing."""
        self.clear()
        if task is None or not task.activity_log:
            return
        t = get_tokens()
        urgency_colors = {
            0: t.urgency_urgent, 1: t.urgency_high,
            2: t.urgency_medium, 3: t.urgency_normal,
        }

        def _row(icon: str, color: str, ts: str, content: str) -> str:
            return (
                f'<p style="margin:3px 0;font-family:Consolas,monospace;font-size:12px;">'
                f'<span style="color:{color};font-weight:bold;">{icon}</span>'
                f' <span style="color:{color};">{ts:>11}</span>'
                f' <span style="color:{t.text_primary};">{content}</span>'
                f'</p>'
            )

        rows: list[str] = []
        for e in reversed(task.activity_log):
            ts = _fmt_ts(e.get("ts", ""), short=True)
            content = e.get("content", "")
            st_val = e.get("status", "")
            entry_urgency = e.get("urgency", getattr(task, "urgency", 3))
            urgency_name = _URGENCY_NAMES.get(entry_urgency, "普通")
            urgency_color = urgency_colors.get(entry_urgency, t.text_secondary)
            if not st_val:
                if "状态切换:" in content or "状态变更:" in content:
                    m = re.search(r"→\s*(\S+)", content)
                    st_val = m.group(1) if m else task.status.value
                else:
                    st_val = task.status.value
            try:
                st = TaskStatus.from_string(st_val)
                sc, sn = st.display_color, st.display_name
            except Exception:
                sc, sn = t.text_secondary, st_val
            is_done = "任务完成" in content
            color = t.timeline_done if is_done else t.timeline_dot
            progress_val = e.get("progress", task.progress)
            rows.append(_row(
                "●", color, ts,
                f'<span style="color:{sc};">[{sn}|{progress_val}%</span>'
                f'<span style="color:{urgency_color};">|{urgency_name}</span>'
                f'<span style="color:{sc};">]</span> {content}',
            ))
        self.setHtml(f'<div>{"".join(rows)}</div>')
