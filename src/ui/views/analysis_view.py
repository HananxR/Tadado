"""活动分析页（page1）构建 — 纯移动自 MainWindow._build_page1（Phase 1）。

TODO(phase4): 槽函数迁入 AnalysisController，替换孤儿 DashboardController。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..calendar_heatmap.activity_content_view import ActivityContentView
from ..calendar_heatmap.collapse_panel import HeatmapCollapsePanel
from ..calendar_heatmap.period_selector import PeriodSelectorBar
from ..calendar_heatmap.task_tree_panel import TaskTreePanel


def build(mw) -> QWidget:
    """Build the Activity Analysis page exactly as MainWindow._build_page1 did."""
    from ..calendar_heatmap.heatmap_stats_panel import HeatmapStatsPanel

    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(8)

    heatmap_label = QLabel("活动热力图")
    heatmap_label.setObjectName("analysisSectionLabel")
    layout.addWidget(heatmap_label)

    ht_row = QWidget()
    ht_layout = QHBoxLayout(ht_row)
    ht_layout.setContentsMargins(0, 0, 0, 0)
    ht_layout.addWidget(mw._heatmap_widget.nav_bar)
    ht_layout.addStretch()
    layout.addWidget(ht_row)

    collapsible = HeatmapCollapsePanel(mw._heatmap_widget)
    layout.addWidget(collapsible, 0)

    # 统计指标：热力图下方右侧（上方导航栏保持清爽）
    stats_row = QWidget()
    stats_layout = QHBoxLayout(stats_row)
    stats_layout.setContentsMargins(0, 0, 4, 0)
    stats_layout.addStretch()
    mw._analysis_stats = HeatmapStatsPanel()
    mw._analysis_stats.setFixedHeight(28)
    # 面板只占内容宽度，左侧 stretch 将其推到行尾（右对齐）
    mw._analysis_stats.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    stats_layout.addWidget(mw._analysis_stats)
    layout.addWidget(stats_row)

    report_label = QLabel("活动报告")
    report_label.setObjectName("analysisSectionLabel")
    layout.addWidget(report_label)

    period_row = QWidget()
    period_layout = QHBoxLayout(period_row)
    period_layout.setContentsMargins(0, 4, 0, 4)
    period_layout.setSpacing(6)

    mw._analysis_period_selector = PeriodSelectorBar()
    mw._analysis_period_selector.period_changed.connect(mw._on_analysis_period_changed)
    period_layout.addWidget(mw._analysis_period_selector, 1)

    mw._analysis_search = QLineEdit()
    mw._analysis_search.setPlaceholderText("搜索活动内容...")
    mw._analysis_search.setFixedWidth(150)
    mw._analysis_search.setFixedHeight(28)
    mw._analysis_search.textChanged.connect(mw._on_analysis_search_changed)
    period_layout.addWidget(mw._analysis_search)

    export_btn = QPushButton("导出")
    export_btn.setObjectName("exportBtn")
    export_btn.setFixedHeight(28)
    export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    export_menu = QMenu(export_btn)
    export_menu.addAction("导出 Markdown", mw._on_export_analysis_md)
    export_menu.addAction("导出 Excel", mw._on_export_analysis_xlsx)
    export_menu.addAction("导出 TXT", mw._on_export_analysis_txt)
    export_btn.setMenu(export_menu)
    export_btn.clicked.connect(lambda: export_btn.showMenu())
    period_layout.addWidget(export_btn)
    layout.addWidget(period_row)

    mw._analysis_splitter = QSplitter(Qt.Orientation.Horizontal)
    mw._analysis_splitter.setHandleWidth(1)
    mw._analysis_splitter.setChildrenCollapsible(False)

    mw._analysis_task_tree = TaskTreePanel(mw._repository)
    mw._analysis_task_tree.tag_selected.connect(mw._on_analysis_tag_selected)
    mw._analysis_splitter.addWidget(mw._analysis_task_tree)

    mw._analysis_content_view = ActivityContentView()
    mw._analysis_content_view.prev_requested.connect(mw._on_analysis_prev)
    mw._analysis_content_view.next_requested.connect(mw._on_analysis_next)
    mw._analysis_splitter.addWidget(mw._analysis_content_view)

    mw._analysis_splitter.setStretchFactor(0, 1)
    mw._analysis_splitter.setStretchFactor(1, 3)
    layout.addWidget(mw._analysis_splitter, 1)

    mw._heatmap_widget.grid.date_clicked.connect(mw._on_heatmap_date_clicked)

    return page
