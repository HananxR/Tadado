"""DashboardController — activity analysis page: build, refresh, export."""

from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...services.task_service import TaskService

_log = logging.getLogger("runlog")


class DashboardController(QObject):
    """Builds and manages the dashboard / activity analysis page.

    Signals:
        status_message(msg): emitted for status-bar flash messages
    """

    status_message = Signal(str)

    def __init__(
        self,
        task_service: TaskService,
        heatmap_widget,  # CalendarHeatmapWidget (shared)
        config,  # AppConfig
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = task_service
        self._heatmap = heatmap_widget
        self._config = config

        # State
        self._built = False
        self._date_range: tuple[date, date] | None = None
        self._partition_id: str | None = None

        # Widgets (created in build_page)
        self._stats = None
        self._period_selector = None
        self._task_tree = None
        self._content_view = None
        self._search_edit = None
        self._splitter = None
        self._export_md_btn = None
        self._export_xlsx_btn = None
        self._export_txt_btn = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_page(self) -> QWidget:
        """Lazily build and return the dashboard page widget."""
        if self._built:
            return self._splitter
        self._built = True

        from ...utils.design_tokens import get_tokens
        t = get_tokens()

        # Stats panel
        from ..calendar_heatmap.heatmap_stats_panel import HeatmapStatsPanel
        self._stats = HeatmapStatsPanel()
        self._stats.setFixedHeight(70)

        # Period selector
        from ..calendar_heatmap.collapse_panel import HeatmapCollapsePanel
        from ..calendar_heatmap.period_selector import PeriodSelectorBar

        heatmap_container = HeatmapCollapsePanel(self._heatmap)
        self._period_selector = PeriodSelectorBar()
        self._period_selector.setFixedHeight(36)

        period_wrapper = QWidget()
        period_wrapper.setStyleSheet(
            f"QWidget {{ background: {t.bg_secondary}; border-radius: 6px; }}"
        )
        period_layout = QVBoxLayout(period_wrapper)
        period_layout.setContentsMargins(6, 2, 6, 2)
        period_layout.addWidget(self._period_selector)

        heatmap_section = QVBoxLayout()
        heatmap_section.setSpacing(4)
        heatmap_section.addWidget(self._stats)
        heatmap_section.addWidget(period_wrapper)
        heatmap_section.addWidget(heatmap_container, 1)

        heatmap_col = QWidget()
        heatmap_col.setLayout(heatmap_section)

        # Analysis content
        from ..calendar_heatmap.activity_content_view import ActivityContentView
        from ..calendar_heatmap.task_tree_panel import TaskTreePanel

        self._task_tree = TaskTreePanel(self._svc._repo)
        self._content_view = ActivityContentView()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索活动内容...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedHeight(28)

        export_bar = QHBoxLayout()
        export_bar.setSpacing(6)
        self._export_md_btn = QPushButton("导出 MD")
        self._export_md_btn.setObjectName("exportMdBtn")
        self._export_md_btn.clicked.connect(lambda: self.export("md"))
        self._export_xlsx_btn = QPushButton("导出 Excel")
        self._export_xlsx_btn.setObjectName("exportXlsxBtn")
        self._export_xlsx_btn.clicked.connect(lambda: self.export("xlsx"))
        self._export_txt_btn = QPushButton("导出 TXT")
        self._export_txt_btn.setObjectName("exportTxtBtn")
        self._export_txt_btn.clicked.connect(lambda: self.export("txt"))
        export_bar.addWidget(self._search_edit, 1)
        export_bar.addWidget(self._export_md_btn)
        export_bar.addWidget(self._export_xlsx_btn)
        export_bar.addWidget(self._export_txt_btn)

        analysis_right = QVBoxLayout()
        analysis_right.setSpacing(6)
        analysis_right.addLayout(export_bar)
        analysis_right.addWidget(self._content_view, 1)

        analysis_right_widget = QWidget()
        analysis_right_widget.setLayout(analysis_right)

        nav_bar = QHBoxLayout()
        nav_bar.setContentsMargins(4, 0, 0, 0)
        prev_btn = QPushButton("◀")
        prev_btn.setFixedSize(28, 22)
        prev_btn.clicked.connect(self._on_prev)
        next_btn = QPushButton("▶")
        next_btn.setFixedSize(28, 22)
        next_btn.clicked.connect(self._on_next)
        self._tag_label = QLabel("")
        nav_bar.addWidget(prev_btn)
        nav_bar.addWidget(next_btn)
        nav_bar.addWidget(self._tag_label)
        nav_bar.addStretch()

        analysis_left = QVBoxLayout()
        analysis_left.setSpacing(6)
        analysis_left.addWidget(self._task_tree, 1)
        analysis_left.addLayout(nav_bar)

        analysis_left_widget = QWidget()
        analysis_left_widget.setLayout(analysis_left)

        self._splitter = QSplitter()
        self._splitter.setObjectName("analysisSplitter")
        self._splitter.addWidget(analysis_left_widget)
        self._splitter.addWidget(analysis_right_widget)
        self._splitter.setSizes([180, 500])

        # Wire signals
        self._heatmap.grid.date_clicked.connect(self._on_date_clicked)
        self._period_selector.period_changed.connect(self._on_period_changed)
        self._task_tree.tag_selected.connect(self._on_tag_selected)
        self._search_edit.textChanged.connect(self._on_search_changed)

        return self._splitter

    def refresh(self, partition_id: str | None = None) -> None:
        """Refresh analysis stats and task tree for a partition."""
        if not self._built:
            return
        self._partition_id = partition_id
        if self._stats and hasattr(self._heatmap, '_model'):
            model = self._heatmap._model
            self._stats.refresh(
                total=model.total_count(),
                active_days=model.active_days(),
                longest_streak=model.longest_streak(),
                daily_avg=model.daily_average(),
            )
        d_from, d_to = self._date_range or (None, None)
        if hasattr(self._task_tree, 'refresh'):
            self._task_tree.refresh(d_from, d_to, partition_id)

    def set_period(self, d_from: date, d_to: date, label: str) -> None:
        """Set analysis date range and refresh."""
        self._date_range = (d_from, d_to)
        if self._built:
            self._heatmap.highlight_range(d_from, d_to)
            self._task_tree.refresh(d_from, d_to, self._partition_id)

    def export(self, fmt: str) -> None:
        """Export analysis to file (md, xlsx, or txt)."""
        if not self._built:
            return
        name_map = self._svc.get_partition_name_map()
        pname = name_map.get(self._partition_id or "", "默认分区")
        d_from, d_to = self._date_range or (date.today(), date.today())
        fname = f"{pname}_{d_from}_{d_to}_{len(self._task_tree.checked_tags)}个标签"
        content = self._content_view.get_plain_text()

        if fmt == "md":
            path, _ = QFileDialog.getSaveFileName(
                self._splitter, "导出 Markdown", f"{fname}.md",
                "Markdown (*.md)",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.status_message.emit(f"已导出: {path}")
        elif fmt == "txt":
            path, _ = QFileDialog.getSaveFileName(
                self._splitter, "导出文本", f"{fname}.txt",
                "Text (*.txt)",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.status_message.emit(f"已导出: {path}")
        elif fmt == "xlsx":
            path, _ = QFileDialog.getSaveFileName(
                self._splitter, "导出 Excel", f"{fname}.xlsx",
                "Excel (*.xlsx)",
            )
            if path:
                rows = self._parse_export_rows(content)
                self._export_xlsx_file(path, rows)
                self.status_message.emit(f"已导出: {path}")

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_date_clicked(self, d: date) -> None:
        if self._built and self._period_selector:
            self._period_selector.set_custom_range(d, d)

    def _on_date_range(self, d_from: date, d_to: date) -> None:
        self.set_period(d_from, d_to, "")

    def _on_period_changed(self, d_from: date, d_to: date, label: str) -> None:
        self.set_period(d_from, d_to, label)

    def _on_tag_selected(self, tag: str) -> None:
        if self._built:
            d_from, d_to = self._date_range or (None, None)
            self._content_view.show_tag_activity(tag, d_from, d_to, self._partition_id)

    def _on_prev(self) -> None:
        if self._built:
            self._task_tree.select_prev()

    def _on_next(self) -> None:
        if self._built:
            self._task_tree.select_next()

    def _on_search_changed(self, text: str) -> None:
        if self._built:
            self._content_view.set_search_text(text)

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def _parse_export_rows(self, content: str) -> list[list[str]]:
        """Parse markdown analysis content into rows for Excel export."""
        rows: list[list[str]] = []
        current_section = ""
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("## "):
                current_section = line[3:]
            elif line.startswith("- "):
                parts = line[2:].split(" ", 3)
                if len(parts) >= 3:
                    rows.append([
                        current_section,
                        parts[0] if len(parts) > 0 else "",
                        parts[1] if len(parts) > 1 else "",
                        parts[2] if len(parts) > 2 else "",
                    ])
        return rows

    def _export_xlsx_file(self, path: str, rows: list[list[str]]) -> None:
        """Write rows to an Excel file."""
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = "活动分析"
        ws.append(["标签", "序号", "任务", "活动信息"])
        for r in rows:
            ws.append(r)
        # Bold header
        for cell in ws[1]:
            cell.font = Font(bold=True)
        wb.save(path)
