"""Activity report panel — tag-grouped task index (left) + report detail (right)."""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...utils.design_tokens import get_tokens
from .report_exporter import export_excel, export_markdown


class ActivityReportPanel(QWidget):
    """Tag-grouped activity report with index + detail split view."""

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
        self._partition_name: str = "默认分区"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header bar ──
        header = QWidget()
        header.setObjectName("reportHeader")
        header.setFixedHeight(36)
        hb = QHBoxLayout(header)
        hb.setContentsMargins(10, 0, 10, 0)
        hb.setSpacing(8)

        self._header_label = QLabel("工作报告")
        self._header_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        hb.addWidget(self._header_label)
        hb.addStretch()

        md_btn = QPushButton("导出 Markdown")
        md_btn.setObjectName("exportBtn")
        md_btn.clicked.connect(self._on_export_md)
        hb.addWidget(md_btn)

        xlsx_btn = QPushButton("导出 Excel")
        xlsx_btn.setObjectName("exportBtn")
        xlsx_btn.clicked.connect(self._on_export_xlsx)
        hb.addWidget(xlsx_btn)

        layout.addWidget(header)

        # ── Splitter: index | detail ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        # Left: tag-grouped task index
        self._index_tree = QTreeWidget()
        self._index_tree.setHeaderHidden(True)
        self._index_tree.setIndentation(16)
        self._index_tree.setAnimated(True)
        self._index_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._index_tree.currentItemChanged.connect(self._on_index_selection_changed)
        self._index_tree.setMinimumWidth(180)
        splitter.addWidget(self._index_tree)

        # Right: report detail card
        self._detail_view = QTextBrowser()
        self._detail_view.setOpenExternalLinks(False)
        self._detail_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        splitter.addWidget(self._detail_view)

        # 40/60 split
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter, 1)

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
        """Extract report data for the given period and rebuild the view."""
        if date_from is None or date_to is None:
            self._show_empty("请通过速览按钮选择时间范围")
            return

        self._report_data = self._extract_report_data(date_from, date_to, partition_id, preset_label)
        self._rebuild_index()
        self._update_header(preset_label, date_from, date_to)

        # Auto-select first task
        if self._index_tree.topLevelItemCount() > 0:
            first_tag = self._index_tree.topLevelItem(0)
            if first_tag.childCount() > 0:
                self._index_tree.setCurrentItem(first_tag.child(0))

    def get_report_data(self) -> dict:
        return self._report_data

    def set_partition_name(self, name: str) -> None:
        self._partition_name = name or "默认分区"

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def _extract_report_data(
        self,
        date_from: date,
        date_to: date,
        partition_id: str | None,
        preset_label: str,
    ) -> dict:
        from ...models.task_filter import TaskFilter

        f = TaskFilter(
            date_from=date_from,
            date_to=date_to,
            partition_id=partition_id,
        )
        tasks = self._repository.search(f)

        tags: dict[str, list[dict]] = {}
        for task in tasks:
            activity_log = task.activity_log or []
            # Filter entries within the date range
            entries_in_range: list[dict] = []
            for entry in activity_log:
                ts_str = entry.get("ts", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    continue
                if date_from <= ts.date() <= date_to:
                    entries_in_range.append(entry)

            if entries_in_range:
                # Sort entries by time
                entries_in_range.sort(key=lambda e: e.get("ts", ""))
                start_progress = entries_in_range[0].get("progress", 0)
                end_progress = entries_in_range[-1].get("progress", 0)
                formatted_entries: list[dict] = []
                for entry in entries_in_range:
                    ts_str2 = entry.get("ts", "")
                    try:
                        ts2 = datetime.fromisoformat(ts_str2)
                        ts_display = ts2.strftime("%m-%d %H:%M")
                    except (ValueError, TypeError):
                        ts_display = ts_str2
                    formatted_entries.append({
                        "ts": ts_display,
                        "status": entry.get("status", ""),
                        "progress": entry.get("progress", 0),
                        "content": entry.get("content", ""),
                    })
            else:
                # No activity entries in range — show task with 0% progress
                start_progress = 0
                end_progress = 0
                formatted_entries = []

            task_info = {
                "task_id": task.id,
                "task_title": task.title or "未命名任务",
                "start_progress": start_progress,
                "end_progress": end_progress,
                "entries": formatted_entries,
            }

            task_tags = task.tags if task.tags else ["未分类"]
            for tag in task_tags:
                tag_key = tag
                tags.setdefault(tag_key, []).append(task_info)

        # Sort tasks within each tag by end_progress desc
        for tag_tasks in tags.values():
            tag_tasks.sort(key=lambda t: -t["end_progress"])

        return {
            "period_label": preset_label,
            "date_range": f"{date_from.isoformat()} ~ {date_to.isoformat()}",
            "tags": tags,
        }

    # ------------------------------------------------------------------
    # Index tree (left panel)
    # ------------------------------------------------------------------

    def _rebuild_index(self) -> None:
        self._index_tree.clear()
        tags: dict = self._report_data.get("tags", {})
        if not tags:
            self._show_empty("该周期内无任务")
            return

        # Sort tags by total tasks
        sorted_tags = sorted(tags.items(), key=lambda kv: -len(kv[1]))
        for i, (tag_name, tasks) in enumerate(sorted_tags):
            tag_item = QTreeWidgetItem()
            tag_item.setText(0, f"{tag_name} ({len(tasks)}个任务)")
            tag_item.setFlags(tag_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            tag_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "tag", "name": tag_name})
            self._index_tree.addTopLevelItem(tag_item)

            for task in tasks:
                task_item = QTreeWidgetItem()
                title = task["task_title"]
                sp = task["start_progress"]
                ep = task["end_progress"]
                entry_count = len(task["entries"])
                delta = f"+{ep - sp}" if ep > sp else f"{ep - sp}"
                task_item.setText(0, title)
                task_item.setToolTip(
                    0, f"{title}\n进度: {sp}% → {ep}% ({delta})\n{entry_count}条活动"
                )
                task_item.setData(0, Qt.ItemDataRole.UserRole, task)
                tag_item.addChild(task_item)

            tag_item.setExpanded(i == 0)

    def _on_index_selection_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        if current is None:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") != "tag":
            self._render_detail(data)

    # ------------------------------------------------------------------
    # Detail view (right panel)
    # ------------------------------------------------------------------

    def _render_detail(self, task_data: dict) -> None:
        t = get_tokens()
        title = task_data.get("task_title", "")
        sp = task_data.get("start_progress", 0)
        ep = task_data.get("end_progress", 0)
        entries: list[dict] = task_data.get("entries", [])

        bg = t.bg_secondary
        text = t.text_primary
        text_sec = t.text_secondary
        accent = t.accent
        border = t.border_primary

        html_parts = [
            '<div style="padding: 16px;">',
            f'<div style="font-size: 16px; font-weight: bold; color: {text}; margin-bottom: 12px;">{title}</div>',
        ]

        # Progress bar
        total_span = max(ep - sp, 0)
        if sp == ep and sp > 0:
            bar_html = f"""
            <div style="margin-bottom: 14px;">
              <div style="font-size: 12px; color: {text_sec}; margin-bottom: 4px;">
                进度: {sp}% (无变化)
              </div>
              <div style="background: {border}; border-radius: 4px; height: 8px; width: 100%;">
                <div style="background: {accent}; border-radius: 4px; height: 8px; width: {min(sp, 100)}%;"></div>
              </div>
            </div>"""
        else:
            bar_html = f"""
            <div style="margin-bottom: 14px;">
              <div style="font-size: 12px; color: {text_sec}; margin-bottom: 4px;">
                进度: {sp}% → {ep}% <span style="color: {accent};">(+{ep - sp}%)</span>
              </div>
              <div style="background: {border}; border-radius: 4px; height: 8px; width: 100%; position: relative;">
                <div style="background: {accent}; border-radius: 4px; height: 8px; width: {min(ep, 100)}%;"></div>
              </div>
            </div>"""
        html_parts.append(bar_html)

        # Timeline entries
        if entries:
            html_parts.append(
                f'<div style="font-size: 12px; font-weight: bold; color: {text_sec};'
                f'margin-bottom: 8px;">工作内容 ({len(entries)}条)</div>'
            )
            for entry in entries:
                ts = entry.get("ts", "")
                status = entry.get("status", "")
                progress = entry.get("progress", 0)
                content = entry.get("content", "")

                dot_color = t.timeline_done if status == "DONE" else t.timeline_dot

                html_parts.append(
                    f'<div style="margin-bottom: 8px; padding-left: 4px;">'
                    f'<span style="color: {dot_color}; font-size: 14px;">●</span> '
                    f'<span style="font-size: 11px; color: {text_sec};">{ts}</span> '
                    f'<span style="font-size: 10px; color: {accent}; background: {accent}18; '
                    f'padding: 1px 6px; border-radius: 3px;">{status}|{progress}%</span>'
                    f'<br>'
                    f'<span style="font-size: 12px; color: {text}; margin-left: 14px;">{content}</span>'
                    f'</div>'
                )
        else:
            html_parts.append(
                f'<div style="font-size: 12px; color: {text_sec};">该周期内无活动记录</div>'
            )

        html_parts.append("</div>")

        self._detail_view.setHtml("\n".join(html_parts))

    def _show_empty(self, message: str) -> None:
        t = get_tokens()
        self._index_tree.clear()
        self._detail_view.setHtml(
            f'<div style="padding: 32px; text-align: center; color: {t.text_secondary}; font-size: 13px;">'
            f'{message}</div>'
        )

    def _update_header(self, preset_label: str, date_from: date, date_to: date) -> None:
        period_names = {
            "yesterday": "昨天日报",
            "today": "今天日报",
            "week": "本周周报",
            "month": "本月月报",
        }
        label = period_names.get(preset_label, f"{preset_label}报告")
        self._header_label.setText(
            f"  {label}  ({date_from.isoformat()} ~ {date_to.isoformat()})"
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export_md(self) -> None:
        period = self._report_data.get("period_label", "报告")
        default_name = f"{self._partition_name}_{period}.md"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown", default_name, "Markdown 文件 (*.md)"
        )
        if path:
            export_markdown(self._report_data, path)

    def _on_export_xlsx(self) -> None:
        period = self._report_data.get("period_label", "报告")
        default_name = f"{self._partition_name}_{period}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Excel", default_name, "Excel 工作簿 (*.xlsx)"
        )
        if path:
            export_excel(self._report_data, path)
