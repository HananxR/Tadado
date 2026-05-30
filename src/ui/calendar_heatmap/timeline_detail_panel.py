"""Timeline detail panel — shows task activity timeline for the selected period."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...models.task import Task
from ...utils.design_tokens import get_tokens
from .report_exporter import export_excel, export_markdown

_STATUS_COLORS = {
    "TODO": "#5b8def",
    "DOING": "#f39c12",
    "DONE": "#2ecc71",
    "OVERDUE": "#e74c3c",
}
_STATUS_LABELS = {
    "TODO": "待办",
    "DOING": "进行中",
    "DONE": "已完成",
    "OVERDUE": "逾期",
}


class TimelineDetailPanel(QWidget):
    """Right-side panel showing task detail with activity timeline."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_task: Task | None = None
        self._current_entries: list[dict] = []
        self._date_from: date | None = None
        self._date_to: date | None = None
        self._build_ui()
        self.show_hint()

    def _build_ui(self) -> None:
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Detail view
        self._detail_view = QTextBrowser()
        self._detail_view.setOpenExternalLinks(False)
        self._detail_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._detail_view.setStyleSheet(
            f"QTextBrowser {{ border: 1px solid {t.border_primary}40; border-radius: 8px; "
            f"background: {t.bg_secondary}; }}"
        )
        layout.addWidget(self._detail_view, 1)

        # Export buttons
        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 4, 0, 0)
        export_row.addStretch()
        md_btn = QPushButton("导出 MD")
        md_btn.setFixedHeight(26)
        md_btn.clicked.connect(self._on_export_md)
        export_row.addWidget(md_btn)
        xlsx_btn = QPushButton("导出 Excel")
        xlsx_btn.setFixedHeight(26)
        xlsx_btn.clicked.connect(self._on_export_xlsx)
        export_row.addWidget(xlsx_btn)
        layout.addLayout(export_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_task(self, task: Task, date_from: date | None, date_to: date | None) -> None:
        """Show activity timeline for a task within the period."""
        self._current_task = task
        self._date_from = date_from
        self._date_to = date_to

        entries = self._parse_log(task)
        if date_from and date_to:
            entries = [e for e in entries if date_from <= self._entry_date(e) <= date_to]

        entries.sort(key=lambda e: e.get("ts", e.get("time", "")))
        self._current_entries = entries

        start_p = entries[0].get("progress", task.progress) if entries else task.progress
        end_p = entries[-1].get("progress", task.progress) if entries else task.progress
        delta = end_p - start_p if entries else 0

        html = self._render_html(task, start_p, end_p, delta, entries)
        self._detail_view.setHtml(html)

    def show_hint(self) -> None:
        """Show hint when no task is selected."""
        t = get_tokens()
        html = f"""<!DOCTYPE html><html><body style="
            font-family: -apple-system, 'Microsoft YaHei', sans-serif;
            display: flex; align-items: center; justify-content: center;
            height: 100%; margin: 0; background: transparent;
        ">
            <div style="text-align: center; color: {t.text_secondary};">
                <div style="font-size: 28px; margin-bottom: 8px;">📋</div>
                <div style="font-size: 12px;">点击左侧任务查看活动详情</div>
            </div>
        </body></html>"""
        self._detail_view.setHtml(html)

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    def _render_html(self, task: Task, start_p: int, end_p: int,
                     delta: int, entries: list[dict]) -> str:
        t = get_tokens()
        status = task.status.value if hasattr(task.status, 'value') else str(task.status)
        dot_color = _STATUS_COLORS.get(status, t.text_secondary)
        tag_str = " ".join(f"#{tag}" if tag.startswith("#") else f"#{tag}"
                           for tag in (task.tags or []))

        delta_sign = "+" if delta >= 0 else ""
        delta_color = t.success if delta > 0 else (t.danger if delta < 0 else t.text_secondary)

        # Progress bar
        bar_html = ""
        if end_p > 0:
            bar_html = f"""
            <div style="display: flex; align-items: center; gap: 8px; margin: 8px 0;">
                <span style="font-size: 10px; color: {t.text_secondary};">{start_p}%</span>
                <div style="flex:1; height:8px; background:{t.bg_secondary}; border-radius:4px;">
                    <div style="width:{end_p}%; height:8px; background:{t.accent};
                         border-radius:4px;"></div>
                </div>
                <span style="font-size: 10px; color: {t.text_secondary};">{end_p}%</span>
                <span style="font-size: 10px; color: {delta_color}; font-weight: bold;">
                    {delta_sign}{delta}%
                </span>
            </div>"""

        # Timeline
        timeline = ""
        if entries:
            timeline = '<div style="margin-top: 12px;">'
            timeline += f'<div style="font-size:11px; font-weight:bold; color:{t.text_primary}; margin-bottom:8px;">活动时间线</div>'
            timeline += f'<div style="border-left:2px solid {t.accent}30; padding-left:16px; margin-left:6px;">'
            for entry in entries:
                ts = entry.get("ts", entry.get("time", ""))
                try:
                    ts_display = datetime.fromisoformat(ts).strftime("%H:%M") if ts else ""
                except (ValueError, TypeError):
                    ts_display = ts[:16] if ts else ""
                entry_status = entry.get("status", "")
                entry_progress = entry.get("progress", 0)
                content = entry.get("content", "")
                sc = _STATUS_COLORS.get(entry_status, t.text_secondary)
                sl = _STATUS_LABELS.get(entry_status, entry_status)

                timeline += f"""
                <div style="margin-bottom: 12px;">
                    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 2px;">
                        <span style="font-size: 9px; color: {t.text_secondary}; min-width: 32px;">
                            {ts_display}
                        </span>
                        <span style="font-size: 8px; background: {sc}18; color: {sc};
                             border-radius: 3px; padding: 1px 6px; font-weight: bold;">
                            {sl}
                        </span>
                        <span style="font-size: 9px; color: {t.text_secondary};">{entry_progress}%</span>
                    </div>
                    <div style="font-size: 11px; color: {t.text_primary}; margin-left: 42px;">
                        {content}
                    </div>
                </div>"""
            timeline += '</div></div>'
        else:
            timeline = f'<div style="margin-top:16px; color:{t.text_secondary}; font-size:11px;">此时段内无活动记录</div>'

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
            body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                   padding: 16px; margin: 0; background: transparent;
                   color: {t.text_primary}; font-size: 11px; line-height: 1.5; }}
        </style></head><body>
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                <span style="font-size: 14px; color: {dot_color};">●</span>
                <span style="font-size: 14px; font-weight: bold;">{task.title}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                <span style="font-size: 9px; color: {t.accent}; background: {t.accent}12;
                     border-radius: 3px; padding: 1px 6px;">{tag_str}</span>
                <span style="font-size: 9px; color: {t.text_secondary};">{len(entries)}条活动</span>
            </div>
            {bar_html}
            {timeline}
        </body></html>"""
        return html

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _build_report_data(self) -> dict:
        task = self._current_task
        entries = self._current_entries
        if not task:
            return {}
        tag = (task.tags or ["__untagged__"])[0]
        return {
            "tags": {
                tag: [{
                    "task_id": task.id,
                    "task_title": task.title,
                    "start_progress": entries[0].get("progress", 0) if entries else 0,
                    "end_progress": entries[-1].get("progress", 0) if entries else 0,
                    "entries": entries,
                }]
            },
            "period_label": "自定义",
            "date_range": f"{self._date_from or ''} ~ {self._date_to or ''}",
        }

    def _on_export_md(self) -> None:
        data = self._build_report_data()
        if not data:
            return
        filepath, _ = QFileDialog.getSaveFileName(self, "导出 Markdown", "", "Markdown (*.md)")
        if filepath:
            export_markdown(data, filepath)

    def _on_export_xlsx(self) -> None:
        data = self._build_report_data()
        if not data:
            return
        filepath, _ = QFileDialog.getSaveFileName(self, "导出 Excel", "", "Excel (*.xlsx)")
        if filepath:
            export_excel(data, filepath)
