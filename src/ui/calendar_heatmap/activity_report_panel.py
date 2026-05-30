"""Activity report panel — HTML-rendered period reports with export."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
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


class ActivityReportPanel(QWidget):
    """HTML-rendered activity report for a selected time period."""

    export_markdown_requested = Signal(dict)
    export_excel_requested = Signal(dict)

    def __init__(
        self,
        repository: TaskRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("activityReportPanel")
        self._repository = repository
        self._report_data: dict = {}
        self._current_search: str = ""
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)

        self._build_ui()

    def _build_ui(self) -> None:
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setObjectName("reportHeader")
        header.setFixedHeight(60)
        hb = QHBoxLayout(header)
        hb.setContentsMargins(12, 6, 12, 6)
        hb.setSpacing(8)

        self._header_title = QLabel("工作报告")
        self._header_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        hb.addWidget(self._header_title)

        self._header_meta = QLabel("")
        self._header_meta.setStyleSheet(f"color: {t.text_secondary}; font-size: 9px;")
        hb.addWidget(self._header_meta)
        hb.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 在报告中搜索...")
        self._search_input.setFixedWidth(180)
        self._search_input.setFixedHeight(26)
        self._search_input.textChanged.connect(self._on_search_changed)
        hb.addWidget(self._search_input)

        md_btn = QPushButton("导出 MD")
        md_btn.setObjectName("exportBtn")
        md_btn.setFixedHeight(26)
        md_btn.clicked.connect(self._on_export_md)
        hb.addWidget(md_btn)

        xlsx_btn = QPushButton("导出 Excel")
        xlsx_btn.setObjectName("exportBtn")
        xlsx_btn.setFixedHeight(26)
        xlsx_btn.clicked.connect(self._on_export_xlsx)
        hb.addWidget(xlsx_btn)

        layout.addWidget(header)

        # ── Report body (HTML) ──
        self._detail_view = QTextBrowser()
        self._detail_view.setOpenExternalLinks(False)
        layout.addWidget(self._detail_view, 1)

        # Show hint by default
        self.show_hint()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(
        self,
        date_from: date | None,
        date_to: date | None,
        partition_id: str | None,
        preset_label: str,
    ) -> None:
        """Extract report data and render."""
        if date_from is None or date_to is None:
            self.show_hint()
            return

        label = preset_label or "自定义"
        self._report_data = self._extract_report_data(date_from, date_to, partition_id, label)
        self._update_header(label, date_from, date_to)
        self._render_full_report(self._report_data, label, date_from, date_to)

    def show_hint(self) -> None:
        """Show placeholder hint."""
        t = get_tokens()
        html = f"""<!DOCTYPE html><html><body style="
            font-family: -apple-system, 'Microsoft YaHei', sans-serif;
            display: flex; align-items: center; justify-content: center;
            height: 100%; margin: 0; background: transparent;
        ">
            <div style="text-align: center; color: {t.text_secondary};">
                <div style="font-size: 32px; margin-bottom: 12px;">📋</div>
                <div style="font-size: 13px;">选择一个时段生成工作报告</div>
                <div style="font-size: 10px; margin-top: 4px;">
                    点击上方【昨天】【今天】【本周】【本月】或选择自定义日期范围
                </div>
            </div>
        </body></html>"""
        self._detail_view.setHtml(html)
        self._header_title.setText("工作报告")
        self._header_meta.setText("")

    def show_task_detail(self, task: Task, date_from: date, date_to: date) -> None:
        """Show detailed report for a single task."""
        label = "自定义"
        self._report_data = self._extract_report_data(date_from, date_to, None, label)
        self._update_header("任务详情", date_from, date_to)
        self._render_task_detail(task, date_from, date_to)

    def get_report_data(self) -> dict:
        return self._report_data

    def set_partition_name(self, name: str) -> None:
        pass  # No longer needed

    # ------------------------------------------------------------------
    # Data extraction (unchanged logic)
    # ------------------------------------------------------------------

    def _extract_report_data(
        self, date_from: date, date_to: date, partition_id: str | None, preset_label: str
    ) -> dict:
        from ...models.task_filter import TaskFilter

        f = TaskFilter(date_from=date_from, date_to=date_to, partition_id=partition_id)
        tasks = self._repository.search(f)

        tags: dict[str, list[dict]] = {}
        total_activities = 0
        total_tasks = 0
        tasks_with_progress = 0

        for task in tasks:
            activity_log = task.activity_log or []
            entries_in_range: list[dict] = []
            for entry in activity_log:
                ts_str = entry.get("ts", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue
                if date_from <= ts.date() <= date_to:
                    entries_in_range.append(entry)

            task_entries = []
            if entries_in_range:
                entries_in_range.sort(key=lambda e: e.get("ts", ""))
                start_progress = entries_in_range[0].get("progress", 0)
                end_progress = entries_in_range[-1].get("progress", 0)
                for entry in entries_in_range:
                    ts_str2 = entry.get("ts", "")
                    try:
                        ts2 = datetime.fromisoformat(ts_str2)
                        ts_display = ts2.strftime("%H:%M")
                    except (ValueError, TypeError):
                        ts_display = ts_str2
                    task_entries.append({
                        "ts": ts_display,
                        "status": entry.get("status", ""),
                        "progress": entry.get("progress", 0),
                        "content": entry.get("content", ""),
                    })
            else:
                start_progress = 0
                end_progress = 0

            if start_progress != end_progress:
                tasks_with_progress += 1

            total_activities += len(task_entries)
            total_tasks += 1

            task_info = {
                "task_id": task.id,
                "task_title": task.title or "未命名任务",
                "start_progress": start_progress,
                "end_progress": end_progress,
                "entries": task_entries,
                "task": task,
            }

            for tag in (task.tags or ["__untagged__"]):
                tags.setdefault(tag, []).append(task_info)

        # Sort tags by total activity count
        sorted_tags = dict(
            sorted(tags.items(), key=lambda x: sum(len(t["entries"]) for t in x[1]), reverse=True)
        )

        date_range_str = f"{date_from.isoformat()} ~ {date_to.isoformat()}"
        return {
            "tags": sorted_tags,
            "total_tasks": total_tasks,
            "total_activities": total_activities,
            "tasks_with_progress": tasks_with_progress,
            "period_label": preset_label,
            "date_range": date_range_str,
            "_label": preset_label,
            "_date_from": date_from,
            "_date_to": date_to,
        }

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    def _update_header(self, label: str, date_from: date, date_to: date) -> None:
        t = get_tokens()
        if date_from == date_to:
            date_str = date_from.strftime("%Y年%m月%d日")
        else:
            date_str = f"{date_from.strftime('%Y-%m-%d')} ~ {date_to.strftime('%Y-%m-%d')}"

        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[date_from.weekday()] if date_from == date_to else ""

        title_map = {"昨天": "昨天日报", "今天": "今天日报", "本周": "本周周报", "本月": "本月月报"}
        title = title_map.get(label, f"{label}报告")
        self._header_title.setText(f"📋 {title}")
        self._header_meta.setText(f"{date_str} {weekday}")

    def _on_search_changed(self, text: str) -> None:
        self._current_search = text
        self._debounce.timeout.connect(self._apply_search)
        self._debounce.start()

    def _apply_search(self) -> None:
        if self._report_data:
            label = self._report_data.get("_label", "")
            d_from = self._report_data.get("_date_from")
            d_to = self._report_data.get("_date_to")
            self._render_full_report(self._report_data, label, d_from, d_to)

    def _task_matches_search(self, task_info: dict) -> bool:
        if not self._current_search:
            return True
        q = self._current_search.lower()
        if q in task_info["task_title"].lower():
            return True
        for entry in task_info.get("entries", []):
            if q in entry.get("content", "").lower():
                return True
        return False

    def _render_full_report(self, data: dict, label: str, date_from: date, date_to: date) -> None:
        t = get_tokens()
        tags = data.get("tags", {})

        # Summary cards HTML
        cards_html = f"""
        <div style="display: flex; gap: 8px; margin-bottom: 16px;">
            <div style="flex: 1; background: {t.accent}08; border: 1px solid {t.border_primary}80;
                 border-radius: 8px; padding: 10px 14px; text-align: center;">
                <div style="font-size: 18px; font-weight: bold; color: {t.accent};">{data['total_tasks']}</div>
                <div style="font-size: 9px; color: {t.text_secondary};">涉及任务</div>
            </div>
            <div style="flex: 1; background: {t.accent}08; border: 1px solid {t.border_primary}80;
                 border-radius: 8px; padding: 10px 14px; text-align: center;">
                <div style="font-size: 18px; font-weight: bold; color: {t.accent};">{data['total_activities']}</div>
                <div style="font-size: 9px; color: {t.text_secondary};">活动记录</div>
            </div>
            <div style="flex: 1; background: {t.accent}08; border: 1px solid {t.border_primary}80;
                 border-radius: 8px; padding: 10px 14px; text-align: center;">
                <div style="font-size: 18px; font-weight: bold; color: {t.accent};">{len(tags)}</div>
                <div style="font-size: 9px; color: {t.text_secondary};">涉及标签</div>
            </div>
            <div style="flex: 1; background: {t.accent}08; border: 1px solid {t.border_primary}80;
                 border-radius: 8px; padding: 10px 14px; text-align: center;">
                <div style="font-size: 18px; font-weight: bold; color: {t.success};">{data['tasks_with_progress']}</div>
                <div style="font-size: 9px; color: {t.text_secondary};">有进展</div>
            </div>
        </div>"""

        # Build tag sections
        tag_sections = ""
        for tag, tasks in tags.items():
            filtered_tasks = [ti for ti in tasks if self._task_matches_search(ti)]
            if not filtered_tasks:
                continue

            tag_display = tag if tag != "__untagged__" else "未分类"
            tag_sections += f"""
            <div style="margin-bottom: 16px;">
                <div style="font-size: 12px; font-weight: bold; color: {t.accent};
                     background: {t.accent}10; display: inline-block; padding: 2px 8px;
                     border-radius: 4px; margin-bottom: 8px;">
                    #{tag_display}
                </div>
                <div style="font-size: 9px; color: {t.text_secondary}; display: inline-block; margin-left: 4px;">
                    {len(filtered_tasks)}个任务, {sum(len(ti['entries']) for ti in filtered_tasks)}条活动
                </div>
            """

            for ti in filtered_tasks:
                tag_sections += self._render_task_card_html(ti, t)

            tag_sections += "</div>"

        if not tag_sections:
            tag_sections = f"""<div style="text-align: center; padding: 32px; color: {t.text_secondary};">
                未找到匹配「{self._current_search}」的任务</div>"""

        # Footer
        active_tasks = [ti for tag, tasks in tags.items() for ti in tasks if ti["entries"]]
        most_active = max(active_tasks, key=lambda x: len(x["entries"]), default=None)
        inactive = [ti for tag, tasks in tags.items() for ti in tasks if not ti["entries"]]

        footer = ""
        if most_active or inactive:
            footer = f"""<div style="margin-top: 16px; padding: 12px;
                background: {t.accent}05; border-radius: 8px; border: 1px solid {t.border_primary}40;
                font-size: 10px; color: {t.text_secondary};">
            """
            if most_active:
                footer += f"""🏆 最活跃: <b style="color: {t.text_primary};">{most_active['task_title']}</b>
                    ({len(most_active['entries'])}条活动)&nbsp;&nbsp;"""
            if inactive:
                names = ", ".join(ti["task_title"] for ti in inactive[:3])
                more = f" 等{len(inactive)}个" if len(inactive) > 3 else ""
                footer += f"""⚠ 无活动记录: {names}{more}"""
            footer += "</div>"

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
            body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                   padding: 16px; margin: 0; background: transparent;
                   color: {t.text_primary}; font-size: 11px; line-height: 1.6; }}
        </style></head><body>
            {cards_html}
            {tag_sections}
            {footer}
        </body></html>"""

        self._detail_view.setHtml(html)

    def _render_task_card_html(self, ti: dict, t) -> str:
        entries = ti.get("entries", [])
        start_p = ti["start_progress"]
        end_p = ti["end_progress"]
        delta = end_p - start_p
        delta_sign = "+" if delta >= 0 else ""
        title = ti["task_title"]

        status = entries[-1]["status"] if entries else "TODO"
        status_color = _STATUS_COLORS.get(status, t.text_secondary)
        status_label = _STATUS_LABELS.get(status, status)
        dot = "●" if entries else "○"

        progress_bar = ""
        if end_p > 0 or start_p > 0:
            bar_width = max(end_p, start_p)
            progress_bar = f"""
            <div style="display: flex; align-items: center; gap: 6px; margin: 4px 0;">
                <span style="font-size: 9px; color: {t.text_secondary};">{start_p}%</span>
                <div style="flex: 1; height: 6px; background: {t.bg_secondary}; border-radius: 3px;">
                    <div style="width: {bar_width}%; height: 6px; background: {t.accent};
                         border-radius: 3px;"></div>
                </div>
                <span style="font-size: 9px; color: {t.text_secondary};">{end_p}%</span>
                <span style="font-size: 9px; color: {t.success}; font-weight: bold;">
                    ({delta_sign}{delta}%)
                </span>
            </div>"""

        # Timeline entries
        timeline = ""
        if entries:
            timeline = '<div style="margin-left: 12px; border-left: 1px solid ' + t.border_primary + '40; padding-left: 12px;">'
            for entry in entries:
                timeline += f"""
                <div style="margin-bottom: 6px;">
                    <span style="font-size: 9px; color: {t.text_secondary}; min-width: 36px; display: inline-block;">
                        {entry['ts']}
                    </span>
                    <span style="font-size: 8px; background: {status_color}20; color: {status_color};
                         border-radius: 3px; padding: 1px 5px; margin: 0 4px;">
                        {_STATUS_LABELS.get(entry['status'], entry['status'])}
                    </span>
                    <span style="font-size: 11px;">{entry['content']}</span>
                </div>"""
            timeline += '</div>'

        return f"""
        <div style="background: {t.accent}03; border-left: 3px solid {status_color};
             border-radius: 6px; padding: 10px 14px; margin-bottom: 8px;">
            <div style="font-size: 12px; font-weight: bold; margin-bottom: 2px;">
                {dot} {title}
                <span style="font-size: 9px; font-weight: normal; color: {t.text_secondary}; margin-left: 6px;">
                    {len(entries)}条活动
                </span>
            </div>
            {progress_bar}
            {timeline}
        </div>"""

    def _render_task_detail(self, task: Task, date_from: date, date_to: date) -> None:
        """Render detailed view for a single task."""
        t = get_tokens()
        entries = []
        activity_log = task.activity_log or []
        for entry in activity_log:
            ts_str = entry.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                continue
            if date_from <= ts.date() <= date_to:
                try:
                    ts_display = ts.strftime("%H:%M")
                except (ValueError, TypeError):
                    ts_display = ts_str
                entries.append({
                    "ts": ts_display,
                    "status": entry.get("status", ""),
                    "progress": entry.get("progress", 0),
                    "content": entry.get("content", ""),
                })

        ti = {
            "task_title": task.title or "未命名任务",
            "start_progress": entries[0]["progress"] if entries else task.progress,
            "end_progress": entries[-1]["progress"] if entries else task.progress,
            "entries": entries,
        }

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
            body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif;
                   padding: 16px; margin: 0; background: transparent;
                   color: {t.text_primary}; font-size: 11px; line-height: 1.6; }}
        </style></head><body>
            {self._render_task_card_html(ti, t)}
        </body></html>"""
        self._detail_view.setHtml(html)

    def show_empty(self, text: str = "") -> None:
        self.show_hint()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export_md(self) -> None:
        if not self._report_data:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown", "", "Markdown (*.md)"
        )
        if filepath:
            export_markdown(self._report_data, filepath)

    def _on_export_xlsx(self) -> None:
        if not self._report_data:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出 Excel", "", "Excel (*.xlsx)"
        )
        if filepath:
            export_excel(self._report_data, filepath)
