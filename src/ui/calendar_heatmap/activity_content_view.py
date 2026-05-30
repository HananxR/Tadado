"""Activity content view — flowing-text summary of tag activity in a period."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...models.task import Task
from ...utils.design_tokens import get_tokens


class ActivityContentView(QWidget):
    """Renders activity entries for a tag as flowing prose text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = QTextBrowser()
        self._view.setOpenExternalLinks(False)
        self._view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._view.setStyleSheet(
            f"QTextBrowser {{ border: none; background: transparent; "
            f"color: {t.text_primary}; font-size: 11px; line-height: 1.6; }}"
        )
        layout.addWidget(self._view, 1)
        self.show_hint()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_tag_activity(self, tag: str, tasks: list[Task],
                          date_from: date | None, date_to: date | None) -> None:
        """Show all activity entries for tasks in a tag, as flowing text."""
        t = get_tokens()
        tag_display = tag if tag != "__untagged__" else "未分类"

        # Collect all entries across tasks, with timestamps
        all_entries: list[tuple[str, str, str]] = []  # (time, content, task_title)
        for task in tasks:
            entries = self._filter_entries(task, date_from, date_to)
            for e in entries:
                ts = e.get("ts", e.get("time", ""))
                try:
                    ts_display = datetime.fromisoformat(ts).strftime("%m-%d %H:%M") if ts else ""
                except (ValueError, TypeError):
                    ts_display = ts[:16] if ts else ""
                content = e.get("content", "")
                if content:
                    all_entries.append((ts_display, content, task.title))

        if not all_entries:
            html = f"""<!DOCTYPE html><html><body style="
                font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                padding: 16px; margin: 0; background: transparent;
                color: {t.text_secondary}; font-size: 11px;
            ">此时段内无活动记录</body></html>"""
            self._view.setHtml(html)
            return

        # Sort by time
        all_entries.sort(key=lambda x: x[0])

        # Build flowing text — one line per task group, entries as inline text
        # Group entries by task
        task_entries: dict[str, list[str]] = {}
        task_order: list[str] = []
        for ts, content, task_title in all_entries:
            if task_title not in task_entries:
                task_entries[task_title] = []
                task_order.append(task_title)
            task_entries[task_title].append(f"{ts} {content}")

        # Build HTML paragraphs
        body_parts = [f'<div style="font-size: 11px; font-weight: bold; color: {t.accent}; '
                      f'margin-bottom: 8px;">#{tag_display}</div>']

        for task_title in task_order:
            entries_text = "；".join(task_entries[task_title])
            body_parts.append(
                f'<p style="margin: 0 0 10px 0; line-height: 1.7; '
                f'color: {t.text_primary}; font-size: 11px;">'
                f'<span style="color: {t.text_secondary};">{task_title}：</span>'
                f'{entries_text}'
                f'</p>'
            )

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
            body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                   padding: 16px; margin: 0; background: transparent;
                   color: {t.text_primary}; font-size: 11px; line-height: 1.6; }}
            p {{ margin: 0 0 10px 0; }}
        </style></head><body>{"".join(body_parts)}</body></html>"""

        self._view.setHtml(html)

    def show_hint(self) -> None:
        t = get_tokens()
        html = f"""<!DOCTYPE html><html><body style="
            font-family: -apple-system, 'Microsoft YaHei', sans-serif;
            display: flex; align-items: center; justify-content: center;
            height: 100%; margin: 0; background: transparent;
        "><div style="text-align: center; color: {t.text_secondary}; font-size: 11px;">
            选择时段和标签查看活动内容</div></body></html>"""
        self._view.setHtml(html)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_entries(self, task: Task, date_from: date | None, date_to: date | None) -> list[dict]:
        entries = self._parse_log(task)
        if date_from is None or date_to is None:
            return entries
        return [e for e in entries if date_from <= self._entry_date(e) <= date_to]

    def _parse_log(self, task: Task) -> list[dict]:
        try:
            raw = task.activity_log
            if not raw or raw == "[]":
                return []
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []

    def _entry_date(self, entry: dict) -> date:
        try:
            ts = entry.get("ts", entry.get("time", ""))
            if "T" in ts:
                return datetime.fromisoformat(ts).date()
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").date()
        except (ValueError, TypeError):
            return date.today()
