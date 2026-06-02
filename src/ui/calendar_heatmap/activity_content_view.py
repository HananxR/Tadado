"""Activity content view — nav bar + ordered-list content for a single tag."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...models.task import Task
from ...utils.design_tokens import get_tokens

_BTN_STYLE = "QPushButton { font-size: 10px; padding: 0px; }"


class ActivityContentView(QWidget):
    """Nav bar (prev/next tag) + activity content rendered as ordered list."""

    prev_requested = Signal()
    next_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Nav bar (left-aligned, compact, same height as left panel top row) ──
        nav = QWidget()
        nav.setFixedHeight(28)
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(2, 3, 4, 3)
        nav_layout.setSpacing(3)

        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedSize(28, 22)
        self._prev_btn.setStyleSheet(_BTN_STYLE)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self.prev_requested.emit)
        nav_layout.addWidget(self._prev_btn)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedSize(28, 22)
        self._next_btn.setStyleSheet(_BTN_STYLE)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self.next_requested.emit)
        nav_layout.addWidget(self._next_btn)

        sep = QLabel("│")
        sep.setObjectName("activitySep")
        sep.setFixedWidth(12)
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(sep)

        self._tag_label = QLabel()
        self._tag_label.setObjectName("activityTagLabel")
        nav_layout.addWidget(self._tag_label)

        nav_layout.addStretch()
        layout.addWidget(nav)

        # ── Separator ──
        hline = QFrame()
        hline.setObjectName("activityHline")
        hline.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(hline)

        # ── Content ──
        self._view = QTextBrowser()
        self._view.setObjectName("activityView")
        self._view.setOpenExternalLinks(False)
        self._view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._view, 1)

        self._plain_text: str = ""
        self._search_text: str = ""
        self._cached_data: dict = {}

        self.show_hint()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_current_tag(self, tag: str, pos: int = 0, total: int = 0) -> None:
        display = tag if tag != "__untagged__" else "未分类"
        if total > 0:
            self._tag_label.setText(f"#{display}({pos}/{total})")
        else:
            self._tag_label.setText(f"#{display}")

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
        t = get_tokens()
        tag_display = tag if tag != "__untagged__" else "未分类"

        items: list[dict] = []
        for task in tasks:
            entries = self._filter_entries(task, date_from, date_to)
            if not entries:
                continue
            entries.sort(key=lambda e: e.get("ts", e.get("time", "")))

            first_status = entries[0].get("status", "")
            last_status = entries[-1].get("status", "")
            first_prog = entries[0].get("progress", 0)
            last_prog = entries[-1].get("progress", 0)

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
            self._view.verticalScrollBar().setValue(0)
            self._cached_data = {}
            self._plain_text = ""
            return

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
            self._view.verticalScrollBar().setValue(0)
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

            html_parts.append(
                f'<div style="margin: 0 0 2px 0; line-height: 1.7;">'
                f'<b>{idx}. {item["title"]}</b> '
                f'<b style="color: {t.danger};">[{status_change}, {prog_change}]</b>:'
                f'</div>'
            )
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
        self._view.verticalScrollBar().setValue(0)

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
