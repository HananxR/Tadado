"""Activity content view — ordered-list format with tag header + task detail."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...models.task import Task
from ...utils.design_tokens import get_tokens


class ActivityContentView(QWidget):
    """Renders activity entries as an ordered list grouped by tag."""

    scrolled_to_bottom = Signal()

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
        sb = self._view.verticalScrollBar()
        sb.valueChanged.connect(self._on_scroll_changed)
        sb.rangeChanged.connect(self._on_scroll_range_changed)
        layout.addWidget(self._view, 1)

        self._plain_text: str = ""
        self._search_text: str = ""
        self._cached_data: dict = {}

        # Debounce timer for scroll-to-bottom detection (200ms)
        self._scroll_debounce = QTimer(self)
        self._scroll_debounce.setSingleShot(True)
        self._scroll_debounce.setInterval(200)
        self._scroll_debounce.timeout.connect(self._check_scroll_bottom)

        self.show_hint()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_search_text(self, text: str) -> None:
        self._search_text = text
        if self._cached_data:
            self._render_from_cache()

    def get_plain_text(self) -> str:
        return self._plain_text

    def show_hint(self) -> None:
        t = get_tokens()
        html = f"""<!DOCTYPE html><html><body style="
            font-family: -apple-system, 'Microsoft YaHei', sans-serif;
            display: flex; align-items: center; justify-content: center;
            height: 100%; margin: 0; background: transparent;
        "><div style="text-align: center; color: {t.text_secondary}; font-size: 11px;">
            选择时段和标签查看活动内容</div></body></html>"""
        self._view.setHtml(html)
        self._plain_text = ""
        self._cached_data = {}

    def show_tag_activity(self, tag: str, tasks: list[Task],
                          date_from: date | None, date_to: date | None) -> None:
        """Show activity for all tasks in a tag as ordered list with detail."""
        t = get_tokens()
        tag_display = tag if tag != "__untagged__" else "未分类"

        # Build ordered list data
        items: list[dict] = []  # each: {title, status_from, status_to, prog_from, prog_to, entry_lines}

        for task in tasks:
            entries = self._filter_entries(task, date_from, date_to)
            if not entries:
                continue
            entries.sort(key=lambda e: e.get("ts", e.get("time", "")))

            # Status/progress change
            first_status = entries[0].get("status", "")
            last_status = entries[-1].get("status", "")
            first_prog = entries[0].get("progress", 0)
            last_prog = entries[-1].get("progress", 0)

            # Format entries with line breaks
            entry_lines: list[str] = []
            for e in entries:
                ts = e.get("ts", e.get("time", ""))
                try:
                    ts_display = datetime.fromisoformat(ts).strftime("%m-%d %H:%M") if ts else ""
                except (ValueError, TypeError):
                    ts_display = ts[:16] if ts else ""
                content = e.get("content", "")
                entry_lines.append(f"{ts_display} {content}")

            items.append({
                "title": task.title,
                "status_from": first_status,
                "status_to": last_status,
                "prog_from": first_prog,
                "prog_to": last_prog,
                "entry_lines": entry_lines,
            })

        if not items:
            html = f"""<!DOCTYPE html><html><body style="
                font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                padding: 16px; margin: 0; background: transparent;
                color: {t.text_secondary}; font-size: 11px;
            ">此时段内无活动记录</body></html>"""
            self._view.setHtml(html)
            self._cached_data = {}
            self._plain_text = ""
            return

        # Apply search filter
        q = self._search_text.lower()
        if q:
            items = [it for it in items
                     if q in it["title"].lower()
                     or any(q in e.lower() for e in it["entry_lines"])]

        if not items:
            html = f"""<!DOCTYPE html><html><body style="
                font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                padding: 16px; margin: 0; background: transparent;
                color: {t.text_secondary}; font-size: 11px;
            ">无匹配结果</body></html>"""
            self._view.setHtml(html)
            return

        # Build HTML
        html_parts = [
            f'<div style="font-size: 12px; font-weight: bold; color: {t.accent}; '
            f'margin-bottom: 8px;">#{tag_display}</div>'
        ]

        plain_text = f"#{tag_display}\n"

        for idx, item in enumerate(items, 1):
            status_change = f"{_status_label(item['status_from'])}→{_status_label(item['status_to'])}"
            prog_change = f"{item['prog_from']}%→{item['prog_to']}%"

            # Ordered item header: number + title bold, status/progress red bold
            html_parts.append(
                f'<div style="margin: 0 0 2px 0; line-height: 1.7;">'
                f'<b>{idx}. {item["title"]}</b> '
                f'<b style="color: {t.danger};">[{status_change}, {prog_change}]</b>:'
                f'</div>'
            )
            # Entry details: each on its own indented line
            entry_html = "".join(
                f'<div style="margin-left: 24px; line-height: 1.7;">{e}</div>'
                for e in item["entry_lines"]
            )
            html_parts.append(entry_html)

            plain_text += f"{idx}. {item['title']} [{status_change}, {prog_change}]:\n"
            for e in item["entry_lines"]:
                plain_text += f"    {e}\n"

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
            body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                   padding: 16px; margin: 0; background: transparent;
                   color: {t.text_primary}; font-size: 11px; line-height: 1.7; }}
        </style></head><body>{"".join(html_parts)}</body></html>"""

        self._view.setHtml(html)
        self._plain_text = plain_text
        self._cached_data = {"tag": tag, "tasks": tasks,
                             "date_from": date_from, "date_to": date_to}
        # Reset scroll to top for new content
        self._view.verticalScrollBar().setValue(0)

    # ------------------------------------------------------------------
    # Scroll detection
    # ------------------------------------------------------------------

    def _at_bottom(self, sb) -> bool:
        """True if scrollbar is at or within 5px of the bottom."""
        return sb.maximum() > 0 and sb.value() >= sb.maximum() - 5

    def _on_scroll_changed(self, value: int) -> None:
        sb = self._view.verticalScrollBar()
        if self._at_bottom(sb):
            self._scroll_debounce.start()
        else:
            self._scroll_debounce.stop()

    def _on_scroll_range_changed(self, _min: int, _max: int) -> None:
        """Re-check scroll position after layout/resize changes scrollbar range."""
        sb = self._view.verticalScrollBar()
        if self._at_bottom(sb):
            self._scroll_debounce.start()

    def _check_scroll_bottom(self) -> None:
        sb = self._view.verticalScrollBar()
        if self._at_bottom(sb):
            self.scrolled_to_bottom.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _render_from_cache(self) -> None:
        d = self._cached_data
        if d:
            self.show_tag_activity(d["tag"], d["tasks"], d["date_from"], d["date_to"])

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


_STATUS_LABEL_MAP = {"TODO": "待办", "DOING": "进行中", "DONE": "已完成", "OVERDUE": "逾期"}


def _status_label(s: str) -> str:
    return _STATUS_LABEL_MAP.get(s, s)
