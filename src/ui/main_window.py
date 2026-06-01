"""Main window — Todoseq-style layout with custom title bar and adaptive sizing."""

from __future__ import annotations

import ctypes
import datetime as dt
from ctypes import wintypes
from datetime import date

from PySide6.QtCore import QDateTime, QSize, Qt, QTime, QTimer
from PySide6.QtGui import (
    QGuiApplication,
    QShortcut, QKeySequence,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..models.repository import TaskRepository
from ..models.task import Task
from ..models.task_filter import TaskFilter, SortCriterion
from ..models.task_status import TaskStatus
from ..services.md_formatter import MarkdownTaskFormatter
from ..services.md_parser import MarkdownTaskParser
from ..utils.icon_loader import load_icon
from ..utils.signal_bus import get_signal_bus
from .calendar_heatmap.calendar_heatmap_widget import CalendarHeatmapWidget
from .calendar_heatmap.collapse_panel import HeatmapCollapsePanel
from .calendar_heatmap.period_selector import PeriodSelectorBar
from .calendar_heatmap.task_tree_panel import TaskTreePanel
from .calendar_heatmap.activity_content_view import ActivityContentView
from ..utils.widget_utils import combo_width
from .widgets.dropdown import DropdownWidget
from .dialogs.about_dialog import AboutDialog
from .dialogs.settings_dialog import SettingsDialog
from .task_list.batch_toolbar import BatchToolbar
from .task_list.task_edit_panel import TaskEditPanel
from .task_list.task_list_model import TaskListModel
from .task_list.task_list_view import TaskListView
from .widgets.filter_bar import FilterBar
from .widgets.progress_dynamics_bar import ProgressDynamicsBar
from .widgets.quick_overview_bar import QuickOverviewBar
from .widgets.status_badge_strip import StatusBadgeStrip


class MainWindow(QMainWindow):
    """Desktop task manager with Markdown-first workflow."""

    def __init__(self, config: AppConfig, repository: TaskRepository) -> None:
        super().__init__()
        self._config = config
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._carousel_filter: TaskFilter | None = None
        self._active_partition_id: str | None = None
        self._partition_passwords: dict[str, str] = {}
        self._page: int = 0
        self._page_size: int = config.get("general", "page_size", default=20)
        self._total_count: int = 0
        self._current_view: str = "edit"
        self._analysis_date_range: tuple = (None, None)

        self.setWindowTitle("DeskTodoSeq")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._setup_custom_title_bar()
        self._setup_status_bar()
        self._setup_central_widget()
        self._setup_idle_lock()
        self._connect_signals()
        self._setup_shortcuts()
        self._setup_midnight_timer()
        self._load_partitions()

    # ------------------------------------------------------------------
    # Adaptive sizing
    # ------------------------------------------------------------------

    def apply_screen_size(self) -> None:
        self.setMinimumSize(900, 600)
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1050, 680)
            return
        geom = screen.availableGeometry()
        w = min(int(geom.width() * 0.65), 1400)
        h = min(int(geom.height() * 0.72), 900)
        self.resize(w, h)
        self.move(
            (geom.width() - w) // 2 + geom.x(),
            (geom.height() - h) // 2 + geom.y(),
        )
        QTimer.singleShot(100, self._sync_header_alignment)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_splitter_sizes()
        self._sync_header_alignment()

    def _apply_splitter_sizes(self) -> None:
        if self._splitter is None:
            return
        total = self._splitter.width()
        if total > 100:
            self._splitter.setSizes([int(total * 0.5), int(total * 0.5)])

    def _sync_header_alignment(self) -> None:
        """Sync editor header height to match table header for vertical alignment."""
        hh = self._task_view.horizontalHeader()
        if hh:
            h = hh.height()
            if h > 0:
                self._edit_panel.set_header_height(h)

    def refresh_theme(self) -> None:
        self._edit_panel.refresh_theme()

    # ------------------------------------------------------------------
    # Custom title bar — VS Code style: icon + menu + window buttons
    # ------------------------------------------------------------------

    def _setup_custom_title_bar(self) -> None:
        from ..utils.design_tokens import get_tokens as _gt
        t = _gt()
        bar_h = 36

        title_bar = QWidget()
        title_bar.setObjectName("customTitleBar")
        title_bar.setFixedHeight(bar_h)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(0)

        # Logo button
        icon_btn = QPushButton()
        icon_btn.setIcon(load_icon("app"))
        icon_btn.setIconSize(QSize(20, 20))
        icon_btn.setFixedSize(bar_h, bar_h)
        icon_btn.setFlat(True)
        icon_btn.setToolTip("返回主界面")
        icon_btn.clicked.connect(self._on_go_home)
        icon_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; padding: 0px; }}"
            f"QPushButton:hover {{ background: {t.accent}20; }}"
        )
        tb.addWidget(icon_btn)

        # Nav buttons (icon + text, flat style)
        btn_style = (
            f"QPushButton {{ border: none; background: transparent; padding: 2px 8px; "
            f"color: {t.text_primary}; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {t.accent}20; }}"
        )
        icon_sz = QSize(18, 18)

        nav_items = [
            ("new_task", "新建单任务", self._on_menu_new_draft),
            ("new_multi_task", "新建多任务", self._on_menu_new_multi),
            ("heatmap", "活动分析", lambda: self._switch_view("dashboard")),
            ("task_manage", "任务管理", lambda: self._switch_view("batch")),
            ("settings", "设置", self._on_settings),
        ]
        for icon_name, text, slot in nav_items:
            btn = QPushButton()
            btn.setIcon(load_icon(icon_name))
            btn.setIconSize(icon_sz)
            btn.setText(text)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        # Help button with dropdown
        help_btn = QPushButton()
        help_btn.setIcon(load_icon("help"))
        help_btn.setIconSize(icon_sz)
        help_btn.setText("帮助")
        help_btn.setFlat(True)
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setStyleSheet(btn_style)
        help_menu = QMenu(help_btn)
        help_menu.addAction("帮助文档(&D)", self._on_help_docs)
        help_menu.addSeparator()
        help_menu.addAction("关于(&A)", self._on_about)
        help_btn.setMenu(help_menu)
        help_btn.clicked.connect(lambda: help_btn.showMenu())
        tb.addWidget(help_btn)

        # Store the right edge of nav buttons for hit-test (logo 36 + ~110px per button * 6 + help ~80px)
        self._title_nav_right = 36 + 110 * 6 + 80

        tb.addStretch()

        # Right-side window buttons (icon only, matching left-side style)
        right_btn_style = (
            f"QPushButton {{ border: none; background: transparent; padding: 0px; }}"
            f"QPushButton:hover {{ background: {t.accent}20; }}"
        )
        right_items = [
            ("tray_hide", "缩小到托盘", self.hide),
            ("fullscreen_toggle", "切换全屏", self._toggle_fullscreen),
            ("window_close", "关闭", self.close),
        ]
        for icon_name, tip, slot in right_items:
            btn = QPushButton()
            btn.setIcon(load_icon(icon_name))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(bar_h, bar_h)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip)
            btn.setStyleSheet(right_btn_style)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        self.setMenuWidget(title_bar)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.apply_screen_size()
        else:
            self.showFullScreen()

    # ------------------------------------------------------------------
    # Win32 native event — window resize + title-bar drag
    # ------------------------------------------------------------------

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0084:  # WM_NCHITTEST
                return self._nc_hit_test(msg)
            elif msg.message == 0x0083 and not msg.wParam:  # WM_NCCALCSIZE
                return True, 0
        return super().nativeEvent(event_type, message)

    def _nc_hit_test(self, msg) -> tuple:
        raw_low = msg.lParam & 0xFFFF
        raw_high = (msg.lParam >> 16) & 0xFFFF
        x = ctypes.c_short(raw_low).value
        y = ctypes.c_short(raw_high).value
        dpr = self.devicePixelRatioF()
        if dpr != 1.0:
            x = int(x / dpr)
            y = int(y / dpr)
        border = 6
        g = self.geometry()
        title_h = 36
        if g.y() <= y < g.y() + title_h:
            # Right-side window buttons area (3 * 36px icon buttons)
            if x >= g.x() + g.width() - 108:
                return False, 0
            # Nav buttons area (logo + icon buttons — must NOT be HTCAPTION)
            nav_right = getattr(self, '_title_nav_right', 700)
            if x < g.x() + nav_right:
                return False, 0
            # Empty stretch area between nav and window buttons = draggable
            return True, 2  # HTCAPTION
        left = x < g.x() + border
        right = x > g.x() + g.width() - border
        top = y < g.y() + border
        bottom = y > g.y() + g.height() - border
        if top and left: return True, 13
        if top and right: return True, 14
        if bottom and left: return True, 16
        if bottom and right: return True, 17
        if left: return True, 10
        if right: return True, 11
        if bottom: return True, 15
        return False, 0

    # ------------------------------------------------------------------
    # Tool bar
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        self._stack = QStackedWidget()

        # === Page 0: Task view ===
        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(8, 4, 8, 4)
        task_layout.setSpacing(2)

        # Row 1: QuickOverviewBar only (presets + carousel)
        self._top_bar = QWidget()
        top_bar_layout = QHBoxLayout(self._top_bar)
        top_bar_layout.setContentsMargins(4, 0, 4, 0)
        top_bar_layout.setSpacing(0)

        self._quick_overview = QuickOverviewBar(self._repository, max_items=2, group_size=2, interval_seconds=5)
        self._quick_overview.preset_activated.connect(self._on_quick_preset)
        self._quick_overview.task_clicked.connect(self._on_carousel_clicked)
        top_bar_layout.addWidget(self._quick_overview, 1)
        task_layout.addWidget(self._top_bar)

        # Heatmap widget (created here, used in heatmap page)
        self._heatmap_widget = CalendarHeatmapWidget(self._repository, self._config)
        self._heatmap_widget.back_requested.connect(lambda: self._switch_view("edit"))

        # Row 2: FilterBar + StatusBadgeStrip (same row, StatusBadgeStrip right-aligned)
        filter_row = QWidget()
        filter_row_layout = QHBoxLayout(filter_row)
        filter_row_layout.setContentsMargins(4, 0, 4, 0)
        filter_row_layout.setSpacing(6)

        self._filter_bar = FilterBar()
        self._filter_bar.set_sort(self._config.default_sort)
        filter_row_layout.addWidget(self._filter_bar, 1)

        self._status_badge = StatusBadgeStrip(self._repository)
        self._status_badge.filter_changed.connect(self._on_filter_changed)
        filter_row_layout.addWidget(self._status_badge)
        task_layout.addWidget(filter_row)

        # Splitter: task list (left) + edit panel (right)
        from PySide6.QtWidgets import QStackedLayout as _QStackedLayout
        self._splitter_container = QWidget()
        self._splitter_stack = _QStackedLayout(self._splitter_container)
        self._splitter_stack.setContentsMargins(0, 0, 0, 0)
        self._splitter_stack.setStackingMode(_QStackedLayout.StackingMode.StackOne)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(False)

        # === Left panel: BatchToolbar + TaskListView + Pagination ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 2, 0)
        left_layout.setSpacing(2)

        self._batch_toolbar = BatchToolbar()
        left_layout.addWidget(self._batch_toolbar)

        self._task_model = TaskListModel()
        self._task_view = TaskListView(self._repository)
        self._task_view.set_model(self._task_model)
        self._task_view.task_selected.connect(self._on_task_selected)
        self._task_view.detail_requested.connect(self._on_detail_requested)
        left_layout.addWidget(self._task_view, 1)

        # Pagination
        page_widget = QWidget()
        page_row = QHBoxLayout(page_widget)
        page_row.setContentsMargins(4, 2, 4, 2)
        page_row.setSpacing(4)
        page_row.addStretch()
        self._prev_page_btn = QPushButton("‹")
        self._prev_page_btn.setObjectName("navBtn")
        self._prev_page_btn.setFixedWidth(28)
        self._prev_page_btn.clicked.connect(self._on_page_prev)
        page_row.addWidget(self._prev_page_btn)
        self._page_label = QLabel("1 / 1")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_row.addWidget(self._page_label)
        self._next_page_btn = QPushButton("›")
        self._next_page_btn.setObjectName("navBtn")
        self._next_page_btn.setFixedWidth(28)
        self._next_page_btn.clicked.connect(self._on_page_next)
        page_row.addWidget(self._next_page_btn)
        page_size_combo = DropdownWidget()
        page_size_combo.setFixedWidth(combo_width(4))
        for n in ["20", "50", "100"]:
            page_size_combo.addItem(n, int(n))
        page_size_combo.setCurrentText(str(self._page_size))
        page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        page_row.addWidget(page_size_combo)
        left_layout.addWidget(page_widget)

        self._splitter.addWidget(left_panel)

        # === Right panel: ProgressDynamicsBar + TaskEditPanel ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(2, 0, 0, 0)
        right_layout.setSpacing(2)

        self._progress_bar = ProgressDynamicsBar(self._repository)
        right_layout.addWidget(self._progress_bar)
        self._progress_bar.progress_filter_activated.connect(self._on_progress_filter)
        self._progress_bar.task_clicked.connect(self._on_carousel_clicked)
        self._progress_bar.set_synced_period("today")

        self._edit_panel = TaskEditPanel(self._repository, self._task_model)
        right_layout.addWidget(self._edit_panel, 1)
        self._splitter.addWidget(right_panel)

        self._splitter_stack.addWidget(self._splitter)
        # Password mask overlay
        self._partition_mask = QWidget()
        self._partition_mask.setObjectName("partitionMask")
        mask_layout = QVBoxLayout(self._partition_mask)
        mask_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mask_hint = QLabel("此分区已加密\n请输入密码查看内容")
        mask_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mask_hint.setStyleSheet(
            "QLabel { font-size: 16px; font-weight: bold;"
            " background: transparent; border: none; }"
        )
        mask_layout.addWidget(mask_hint)
        unlock_btn = QPushButton("输入密码解锁")
        unlock_btn.setObjectName("saveBtn")
        unlock_btn.setFixedWidth(140)
        unlock_btn.clicked.connect(self._on_unlock_partition)
        mask_btn_row = QHBoxLayout()
        mask_btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mask_btn_row.addWidget(unlock_btn)
        mask_layout.addLayout(mask_btn_row)
        self._splitter_stack.addWidget(self._partition_mask)
        self._splitter_stack.setCurrentIndex(0)
        task_layout.addWidget(self._splitter_container, 1)

        self._stack.addWidget(task_page)

        # === Page 1: Activity Analysis ===
        analysis_page = QWidget()
        analysis_layout = QVBoxLayout(analysis_page)
        analysis_layout.setContentsMargins(12, 8, 12, 8)
        analysis_layout.setSpacing(8)

        from .calendar_heatmap.heatmap_stats_panel import HeatmapStatsPanel
        from ..utils.design_tokens import get_tokens as _gt3
        t_tok = _gt3()
        sec_style = (
            f"font-size: 12px; font-weight: bold; color: {t_tok.text_primary}; "
            f"padding: 2px 0 4px 0; border-bottom: 1px solid {t_tok.border_primary};"
        )

        # ── Section: Heatmap ──
        heatmap_label = QLabel("活动热力图")
        heatmap_label.setStyleSheet(sec_style)
        analysis_layout.addWidget(heatmap_label)

        # Nav bar + stats (same row)
        heatmap_top_row = QWidget()
        heatmap_top_layout = QHBoxLayout(heatmap_top_row)
        heatmap_top_layout.setContentsMargins(0, 0, 0, 0)
        heatmap_top_layout.addWidget(self._heatmap_widget.nav_bar)
        heatmap_top_layout.addStretch()
        self._analysis_stats = HeatmapStatsPanel()
        self._analysis_stats.setFixedHeight(28)
        heatmap_top_layout.addWidget(self._analysis_stats)
        analysis_layout.addWidget(heatmap_top_row)

        # Heatmap grid
        collapsible = HeatmapCollapsePanel(self._heatmap_widget)
        analysis_layout.addWidget(collapsible, 0)

        # ── Section: Report ──
        report_label = QLabel("活动报告")
        report_label.setStyleSheet(sec_style)
        analysis_layout.addWidget(report_label)

        # Period selector + search + export (same row)
        period_row = QWidget()
        period_row_layout = QHBoxLayout(period_row)
        period_row_layout.setContentsMargins(0, 4, 0, 4)
        period_row_layout.setSpacing(6)

        self._analysis_period_selector = PeriodSelectorBar()
        self._analysis_period_selector.period_changed.connect(self._on_analysis_period_changed)
        period_row_layout.addWidget(self._analysis_period_selector, 1)

        self._analysis_search = QLineEdit()
        self._analysis_search.setPlaceholderText("搜索活动内容...")
        self._analysis_search.setFixedWidth(150)
        self._analysis_search.setFixedHeight(28)
        self._analysis_search.setStyleSheet("font-size: 11px;")
        self._analysis_search.textChanged.connect(self._on_analysis_search_changed)
        period_row_layout.addWidget(self._analysis_search)

        btn_style = (
            f"QPushButton {{ background: transparent; color: {t_tok.text_primary}; "
            f"border: 1px solid {t_tok.border_primary}; border-radius: 4px; "
            f"padding: 2px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {t_tok.accent}20; }}"
        )
        export_btn = QPushButton("导出")
        export_btn.setFixedHeight(28)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setStyleSheet(btn_style)
        export_menu = QMenu(export_btn)
        export_menu.addAction("导出 Markdown", self._on_export_analysis_md)
        export_menu.addAction("导出 Excel", self._on_export_analysis_xlsx)
        export_menu.addAction("导出 TXT", self._on_export_analysis_txt)
        export_btn.setMenu(export_menu)
        export_btn.clicked.connect(lambda: export_btn.showMenu())
        period_row_layout.addWidget(export_btn)

        analysis_layout.addWidget(period_row)

        # Tag list (left) + Content view (right)
        self._analysis_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._analysis_splitter.setHandleWidth(1)
        self._analysis_splitter.setChildrenCollapsible(False)

        self._analysis_task_tree = TaskTreePanel(self._repository)
        self._analysis_task_tree.tag_selected.connect(self._on_analysis_tag_selected)
        self._analysis_splitter.addWidget(self._analysis_task_tree)

        self._analysis_content_view = ActivityContentView()
        self._analysis_content_view.scrolled_to_bottom.connect(self._on_content_scrolled_to_bottom)
        self._analysis_splitter.addWidget(self._analysis_content_view)

        self._analysis_splitter.setStretchFactor(0, 1)  # ~25%
        self._analysis_splitter.setStretchFactor(1, 3)  # ~75%
        analysis_layout.addWidget(self._analysis_splitter, 1)

        # Connect heatmap grid signals
        self._heatmap_widget.grid.date_clicked.connect(self._on_heatmap_date_clicked)

        self._stack.addWidget(analysis_page)

        # === Page 2: Batch Processing ===
        batch_page = QWidget()
        batch_layout = QVBoxLayout(batch_page)
        batch_layout.setContentsMargins(8, 4, 8, 4)
        batch_layout.setSpacing(4)

        # Top: filter bar (compact)
        batch_filter_row = QWidget()
        batch_filter_row_layout = QHBoxLayout(batch_filter_row)
        batch_filter_row_layout.setContentsMargins(0, 0, 0, 0)
        batch_filter_row_layout.setSpacing(6)
        self._batch_filter_bar = FilterBar()
        self._batch_filter_bar.filter_changed.connect(self._on_batch_filter_changed)
        batch_filter_row_layout.addWidget(self._batch_filter_bar, 1)
        # Import / Export
        import_btn = QPushButton("📥 导入 MD")
        import_btn.setFixedHeight(28)
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.clicked.connect(self._on_import)
        batch_filter_row_layout.addWidget(import_btn)

        export_btn = QPushButton("📤 导出 MD")
        export_btn.setFixedHeight(28)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._on_export)
        batch_filter_row_layout.addWidget(export_btn)

        back_btn2 = QPushButton("↩ 返回编辑")
        back_btn2.setFixedHeight(28)
        back_btn2.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn2.clicked.connect(lambda: self._switch_view("edit"))
        batch_filter_row_layout.addWidget(back_btn2)
        batch_layout.addWidget(batch_filter_row)

        # Operation toolbar
        self._batch_toolbar2 = BatchToolbar()
        self._batch_toolbar2.batch_status_change.connect(self._on_batch_status_change)
        self._batch_toolbar2.batch_delete.connect(self._on_batch_delete)
        self._batch_toolbar2.batch_suspend.connect(self._on_batch_suspend)
        self._batch_toolbar2.batch_restart.connect(self._on_batch_restart)
        self._batch_toolbar2.select_all_requested.connect(self._on_batch_select_all)
        self._batch_toolbar2.deselect_all_requested.connect(self._on_batch_deselect_all)
        batch_layout.addWidget(self._batch_toolbar2)

        # Task table (full width, no edit panel)
        self._batch_task_model = TaskListModel()
        self._batch_task_view = TaskListView(self._repository)
        self._batch_task_view.setModel(self._batch_task_model)
        self._batch_task_view.setSelectionBehavior(
            self._batch_task_view.SelectionBehavior.SelectRows
        )
        # Track checkbox changes via model dataChanged
        self._batch_task_model.dataChanged.connect(self._on_batch_model_data_changed)
        batch_layout.addWidget(self._batch_task_view, 1)

        # Pagination row
        batch_pager = QWidget()
        batch_pager_layout = QHBoxLayout(batch_pager)
        batch_pager_layout.setContentsMargins(0, 0, 0, 0)
        batch_pager_layout.addStretch()
        self._batch_total_label = QLabel("共 0 项")
        self._batch_total_label.setStyleSheet("font-size: 10px;")
        batch_pager_layout.addWidget(self._batch_total_label)
        batch_pager_layout.addSpacing(8)
        self._batch_prev_btn = QPushButton("‹ 上一页")
        self._batch_prev_btn.setFixedHeight(24)
        self._batch_prev_btn.clicked.connect(self._on_batch_page_prev)
        batch_pager_layout.addWidget(self._batch_prev_btn)
        self._batch_page_label = QLabel("1 / 1 页")
        self._batch_page_label.setStyleSheet("font-size: 10px;")
        batch_pager_layout.addWidget(self._batch_page_label)
        self._batch_next_btn = QPushButton("下一页 ›")
        self._batch_next_btn.setFixedHeight(24)
        self._batch_next_btn.clicked.connect(self._on_batch_page_next)
        batch_pager_layout.addWidget(self._batch_next_btn)
        batch_pager_layout.addStretch()
        batch_layout.addWidget(batch_pager)

        # Confirm bar (hidden by default, slides up)
        self._confirm_bar = QWidget()
        self._confirm_bar.setFixedHeight(48)
        self._confirm_bar.setVisible(False)
        confirm_layout = QHBoxLayout(self._confirm_bar)
        confirm_layout.setContentsMargins(12, 4, 12, 4)
        self._confirm_label = QLabel("")
        confirm_layout.addWidget(self._confirm_label, 1)
        self._confirm_ok_btn = QPushButton("确认")
        self._confirm_ok_btn.setFixedHeight(28)
        confirm_layout.addWidget(self._confirm_ok_btn)
        confirm_cancel_btn = QPushButton("取消")
        confirm_cancel_btn.setFixedHeight(28)
        confirm_cancel_btn.clicked.connect(self._hide_confirm)
        confirm_layout.addWidget(confirm_cancel_btn)
        batch_layout.addWidget(self._confirm_bar)

        self._stack.addWidget(batch_page)
        self._batch_page = 0
        self._batch_page_size = 20
        self._batch_total_count = 0
        self._batch_current_filter = TaskFilter()
        self._batch_pending_action: dict = {}

        self.setCentralWidget(self._stack)

    def _on_new_multi_task(self) -> None:
        if not self.isVisible() and self._edit_panel.has_unsaved_draft():
            self._edit_panel.discard_draft()
        elif not self._guard_draft():
            return
        if self._splitter_stack.currentIndex() == 1:
            if self._partition_passwords.get(self._active_partition_id, ""):
                self._on_unlock_partition()
                if self._splitter_stack.currentIndex() == 1:
                    return
            else:
                self._splitter_stack.setCurrentIndex(0)
        self._stack.setCurrentIndex(0)
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self._edit_panel.set_active_partition(self._active_partition_id)
        self._edit_panel.create_draft_multi()
        self._apply_splitter_sizes()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        from ..utils.design_tokens import get_tokens as _gt2
        t = _gt2()

        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(True)

        # Partition selector button (prominent, left side)
        self._status_partition_btn = QPushButton("📁 切换分区")
        self._status_partition_btn.setFlat(True)
        self._status_partition_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status_partition_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; padding: 2px 8px; "
            f"font-size: 11px; font-weight: bold; color: {t.accent if t else '#5b8def'}; }}"
            f"QPushButton:hover {{ background: {t.accent}15; border-radius: 4px; }}"
        )
        self._status_partition_menu = QMenu(self._status_partition_btn)
        self._status_partition_btn.setMenu(self._status_partition_menu)
        self._status_partition_btn.clicked.connect(lambda: self._status_partition_btn.showMenu())
        self._status_bar.addWidget(self._status_partition_btn)

        # Stats + motd text
        self._status_msg = QLabel("就绪")
        self._status_bar.addWidget(self._status_msg, 1)

        # Right: clock
        self._status_clock = QLabel()
        self._status_clock.setStyleSheet("QLabel { margin-right: 4px; }")
        self._status_bar.addPermanentWidget(self._status_clock)
        self._update_status_clock()
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_status_clock)
        self._clock_timer.start(1000)
        self.setStatusBar(self._status_bar)

    def _update_status_clock(self) -> None:
        self._status_clock.setText(dt.datetime.now().strftime("%Y年%m月%d日 %I:%M:%S %p"))

    # ------------------------------------------------------------------
    # Idle lock timer
    # ------------------------------------------------------------------

    def _setup_idle_lock(self) -> None:
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(30_000)
        self._idle_timer.timeout.connect(self._check_idle_lock)
        self._idle_timer.start()
        self._last_activity: dt.datetime | None = None

    def _check_idle_lock(self) -> None:
        mins = self._config.get("general", "auto_lock_minutes", default=10)
        if not mins or mins <= 0:
            return
        if self._splitter_stack.currentIndex() == 1:
            return
        if self._last_activity is None:
            self._last_activity = dt.datetime.now()
            return
        elapsed = (dt.datetime.now() - self._last_activity).total_seconds() / 60.0
        if elapsed >= mins / 2.0 and self._partition_passwords.get(self._active_partition_id, ""):
            self._idle_timer.stop()
            self._lock_partition(self._active_partition_id)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        bus = self._signal_bus
        bus.scan_completed.connect(self._on_data_changed)
        bus.task_created.connect(self._on_task_created)
        bus.task_updated.connect(self._on_data_changed)
        bus.task_deleted.connect(self._on_task_deleted)
        bus.task_status_changed.connect(self._on_data_changed)
        bus.batch_operation_completed.connect(self._on_batch_completed)
        bus.tasks_bulk_created.connect(self._on_tasks_bulk_created)
        self._filter_bar.filter_changed.connect(self._on_filter_changed)
        bus.partitions_changed.connect(self._on_partitions_changed)
        bus.config_changed.connect(self._on_config_changed)
        bus.archive_completed.connect(self._on_data_changed)

        bus.task_created.connect(self._on_heatmap_data_changed)
        bus.task_updated.connect(self._on_heatmap_data_changed)
        bus.task_deleted.connect(self._on_heatmap_data_changed)
        bus.task_status_changed.connect(self._on_heatmap_data_changed)
        bus.batch_operation_completed.connect(self._on_heatmap_data_changed)

        self._task_model.dataChanged.connect(self._on_model_data_changed)

        self._batch_toolbar.select_all_requested.connect(self._on_edit_select_all)
        self._batch_toolbar.deselect_all_requested.connect(self._on_edit_deselect_all)
        self._batch_toolbar.batch_status_change.connect(self._on_batch_status_change)
        self._batch_toolbar.batch_delete.connect(self._on_batch_delete)
        self._batch_toolbar.batch_suspend.connect(self._on_batch_suspend)
        self._batch_toolbar.batch_restart.connect(self._on_batch_restart)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_task)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_refresh)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self._switch_view("edit"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self._switch_view("dashboard"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self._switch_view("batch"))
        QShortcut(QKeySequence("Escape"), self, activated=self._on_escape)

    # ------------------------------------------------------------------
    # Slots: data refresh
    # ------------------------------------------------------------------

    def _on_data_changed(self, *args) -> None:
        if hasattr(self, '_splitter_stack') and self._splitter_stack.currentIndex() == 1:
            return
        if hasattr(self, '_progress_bar'):
            self._progress_bar.reset_to_unclicked()
        _sizes = self._splitter.sizes() if hasattr(self, '_splitter') and self._splitter else None
        f = self._carousel_filter or TaskFilter()
        self._refresh_all_views(f, reset_page=False)
        if _sizes:
            self._splitter.setSizes(_sizes)

    def _on_tasks_bulk_created(self, count: int, task_ids: list) -> None:
        """Handle multi-task creation: refresh + bold all + move to top + open first."""
        self._on_data_changed()
        self._task_model.set_bold_tasks(set(task_ids))
        # Move all batch tasks to top (reverse preserves order)
        for tid in reversed(task_ids):
            for row in range(self._task_model.rowCount()):
                if self._task_model.tasks[row].id == tid and row > 0:
                    self._task_model.move_to_top(row)
                    break
        self._on_task_selected(self._task_model.tasks[0])

    def _refresh_all_views(self, filter_: TaskFilter, reset_page: bool = True) -> None:
        if reset_page:
            self._reset_pagination()
        filter_.partition_id = self._active_partition_id
        tasks = self._repository.search(filter_)
        self._total_count = self._repository.count(filter_)
        self._task_model.load_tasks(tasks)
        self._quick_overview.set_items(tasks)
        self._update_page_label()
        self._update_status_bar(filter_)
        self._status_badge.refresh(filter_.date_from, filter_.date_to)
        self._progress_bar.set_items(tasks)

    def _on_task_created(self, task) -> None:
        self._filter_bar.reset()
        self._on_data_changed()
        # Move new task to top
        for row in range(self._task_model.rowCount()):
            if self._task_model.tasks[row].id == task.id and row > 0:
                self._task_model.move_to_top(row)
                break
        self._on_task_selected(task)

    def _select_and_load_task(self, task_id: str) -> None:
        """Select a task in the list and load it in the edit panel."""
        model = self._task_view.model()
        if model is None:
            return
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            t = idx.data(Qt.ItemDataRole.UserRole)
            if t and t.id == task_id:
                self._task_view.selectRow(row)
                self._task_view.scrollTo(idx)
                self._on_task_selected(t)
                return

    def _on_task_deleted(self, task_id: str) -> None:
        self._on_data_changed()

    def _on_batch_completed(self) -> None:
        self._on_data_changed()

    # ------------------------------------------------------------------
    # Batch page methods
    # ------------------------------------------------------------------

    def _refresh_batch_page(self) -> None:
        """Refresh the batch processing page."""
        if not hasattr(self, '_batch_task_model'):
            return
        self._batch_page = 0
        f = self._batch_current_filter or TaskFilter()
        f.partition_id = self._active_partition_id
        f.limit = self._batch_page_size
        f.offset = self._batch_page * self._batch_page_size
        tasks = self._repository.search(f)
        self._batch_total_count = self._repository.count(f)
        self._batch_task_model.load_tasks(tasks)
        self._update_batch_pagination()

    def _update_batch_pagination(self) -> None:
        total_pages = max(1, (self._batch_total_count + self._batch_page_size - 1) // self._batch_page_size)
        self._batch_total_label.setText(f"共 {self._batch_total_count} 项")
        self._batch_page_label.setText(f"{self._batch_page + 1} / {total_pages} 页")
        self._batch_prev_btn.setEnabled(self._batch_page > 0)
        self._batch_next_btn.setEnabled(self._batch_page < total_pages - 1)

    def _on_batch_filter_changed(self, filter_: TaskFilter) -> None:
        self._batch_current_filter = filter_
        self._refresh_batch_page()

    def _on_batch_page_prev(self) -> None:
        if self._batch_page > 0:
            self._batch_page -= 1
            self._refresh_batch_page()

    def _on_batch_page_next(self) -> None:
        total_pages = max(1, (self._batch_total_count + self._batch_page_size - 1) // self._batch_page_size)
        if self._batch_page < total_pages - 1:
            self._batch_page += 1
            self._refresh_batch_page()

    def _on_edit_select_all(self) -> None:
        if hasattr(self, '_task_model'):
            ids = set(t.id for t in self._task_model.tasks)
            self._task_model.set_checked_ids(ids)

    def _on_edit_deselect_all(self) -> None:
        if hasattr(self, '_task_model'):
            self._task_model.set_checked_ids(set())

    def _on_batch_select_all(self) -> None:
        if hasattr(self, '_batch_task_model'):
            ids = set(t.id for t in self._batch_task_model.tasks)
            self._batch_task_model.set_checked_ids(ids)

    def _on_batch_deselect_all(self) -> None:
        if hasattr(self, '_batch_task_model'):
            self._batch_task_model.set_checked_ids(set())

    def _on_batch_model_data_changed(self) -> None:
        if hasattr(self, '_batch_toolbar2'):
            ids = self._batch_task_model.checked_task_ids()
            self._batch_toolbar2.set_selected(ids)

    def _on_batch_status_change(self, ids: list[str], status) -> None:
        if self._current_view == "edit":
            reply = QMessageBox.question(
                self, "确认操作",
                f"确认更改 {len(ids)} 个任务的状态？",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self._repository.batch_update_status(ids, status)
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
        else:
            self._confirm_label.setText(f"确认更改 {len(ids)} 个任务的状态？")
            self._confirm_bar.setVisible(True)
            self._batch_pending_action = {"action": "status", "ids": ids, "status": status}
            self._confirm_ok_btn.clicked.disconnect()
            self._confirm_ok_btn.clicked.connect(self._execute_batch_status)

    def _execute_batch_status(self) -> None:
        action = self._batch_pending_action
        self._repository.batch_update_status(action["ids"], action["status"])
        self._hide_confirm()
        self._refresh_batch_page()
        self._on_data_changed()

    def _on_batch_delete(self, ids: list[str]) -> None:
        if self._current_view == "edit":
            reply = QMessageBox.question(
                self, "确认删除",
                f"确认删除 {len(ids)} 个任务？此操作不可撤销。",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self._repository.batch_delete(ids)
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
        else:
            self._confirm_label.setText(f"⚠ 确认删除 {len(ids)} 个任务？此操作不可撤销。")
            self._confirm_bar.setVisible(True)
            self._batch_pending_action = {"action": "delete", "ids": ids}
            self._confirm_ok_btn.clicked.disconnect()
            self._confirm_ok_btn.clicked.connect(self._execute_batch_delete)

    def _execute_batch_delete(self) -> None:
        action = self._batch_pending_action
        self._repository.batch_delete(action["ids"])
        self._hide_confirm()
        self._refresh_batch_page()
        self._on_data_changed()

    def _on_batch_suspend(self, ids: list[str]) -> None:
        if self._current_view == "edit":
            reply = QMessageBox.question(
                self, "确认操作",
                f"确认中止 {len(ids)} 个任务？",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self._repository.batch_suspend(ids)
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
        else:
            self._confirm_label.setText(f"确认中止 {len(ids)} 个任务？")
            self._confirm_bar.setVisible(True)
            self._batch_pending_action = {"action": "suspend", "ids": ids}
            self._confirm_ok_btn.clicked.disconnect()
            self._confirm_ok_btn.clicked.connect(self._execute_batch_suspend)

    def _execute_batch_suspend(self) -> None:
        action = self._batch_pending_action
        self._repository.batch_suspend(action["ids"])
        self._hide_confirm()
        self._refresh_batch_page()
        self._on_data_changed()

    def _on_batch_restart(self, ids: list[str]) -> None:
        if self._current_view == "edit":
            reply = QMessageBox.question(
                self, "确认操作",
                f"确认重启 {len(ids)} 个任务？",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self._repository.batch_restart(ids)
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
        else:
            self._confirm_label.setText(f"确认重启 {len(ids)} 个任务？")
            self._confirm_bar.setVisible(True)
            self._batch_pending_action = {"action": "restart", "ids": ids}
            self._confirm_ok_btn.clicked.disconnect()
            self._confirm_ok_btn.clicked.connect(self._execute_batch_restart)

    def _execute_batch_restart(self) -> None:
        action = self._batch_pending_action
        self._repository.batch_restart(action["ids"])
        self._hide_confirm()
        self._refresh_batch_page()
        self._on_data_changed()

    def _hide_confirm(self) -> None:
        self._confirm_bar.setVisible(False)
        self._batch_pending_action = {}

    def _on_filter_changed(self, filter_: TaskFilter) -> None:
        self._carousel_filter = filter_
        self._refresh_all_views(filter_)

    def _on_quick_preset(self, preset: str) -> None:
        f = TaskFilter()
        if preset == "all":
            pass
        elif preset == "today":
            today = date.today()
            f.date_from = today
            f.date_to = date.today()
        elif preset == "yesterday":
            yesterday = date.today() - dt.timedelta(days=1)
            f.date_from = yesterday
            f.date_to = yesterday
        elif preset == "last_week":
            today = date.today()
            f.date_from = today - dt.timedelta(days=today.isoweekday() + 6)
            f.date_to = f.date_from + dt.timedelta(days=6)
        elif preset == "week":
            today = date.today()
            f.date_from = today - dt.timedelta(days=today.isoweekday() - 1)
            f.date_to = f.date_from + dt.timedelta(days=6)
        elif preset == "last_month":
            today = date.today()
            first_of_this_month = today.replace(day=1)
            last_day_of_last_month = first_of_this_month - dt.timedelta(days=1)
            first_of_last_month = last_day_of_last_month.replace(day=1)
            f.date_from = first_of_last_month
            f.date_to = last_day_of_last_month
        elif preset == "month":
            today = date.today()
            f.date_from = today.replace(day=1)
        elif "days" in preset:
            try:
                days = int(preset.split("_")[0])
                today = date.today()
                f.date_from = today - dt.timedelta(days=days)
                f.date_to = today
            except ValueError:
                pass
        self._carousel_filter = f
        self._refresh_all_views(f)
        self._progress_bar.set_synced_period(preset)
        if self._current_view != "edit":
            self._heatmap_widget.highlight_range(f.date_from, f.date_to, preset)

    def _on_status_clicked(self, status: TaskStatus) -> None:
        f = TaskFilter(statuses=[status])
        if self._carousel_filter:
            f.tags = list(self._carousel_filter.tags)
        self._carousel_filter = f
        self._refresh_all_views(f)

    def _on_progress_filter(self, filter_: TaskFilter) -> None:
        self._carousel_filter = filter_
        self._refresh_all_views(filter_)
        if self._task_model.tasks:
            self._on_task_selected(self._task_model.tasks[0])

    def _on_task_selected(self, task: Task) -> None:
        self._task_model.set_highlighted_task(task.id)
        self._task_model.set_bold_tasks(set())  # clear batch bold
        self._edit_panel.load_task(task)
        self._last_activity = dt.datetime.now()

    def _on_detail_requested(self, task: Task) -> None:
        self._edit_panel.load_task(task)

    def _on_task_selection_changed(self) -> None:
        selected = self._task_view.selected_task_ids()
        self._batch_toolbar.setVisible(len(selected) >= 1)

    def _on_model_data_changed(self) -> None:
        if hasattr(self, '_batch_toolbar'):
            ids = self._task_model.checked_task_ids()
            self._batch_toolbar.set_selected(ids)

    def _on_carousel_clicked(self, task_id: str) -> None:
        self._select_and_load_task(task_id)

    def _on_heatmap_data_changed(self, *args) -> None:
        if hasattr(self, '_heatmap_widget'):
            self._heatmap_widget.force_refresh()

    def _on_go_home(self) -> None:
        if self._current_view != "edit":
            self._switch_view("edit")
        self._carousel_filter = None
        self._filter_bar.reset()
        self._on_data_changed()
        self._last_activity = dt.datetime.now()

    def _on_escape(self) -> None:
        if self._current_view != "edit":
            self._switch_view("edit")
        else:
            self._on_go_home()

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _update_page_label(self) -> None:
        if self._page_size <= 0:
            self._page_label.setText("全部")
            return
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        self._page_label.setText(f"{self._page + 1} / {total_pages}")

    def _on_page_prev(self) -> None:
        if self._page > 0:
            self._page -= 1
            f = self._carousel_filter or TaskFilter()
            self._refresh_all_views(f, reset_page=False)

    def _on_page_next(self) -> None:
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        if self._page < total_pages - 1:
            self._page += 1
            f = self._carousel_filter or TaskFilter()
            self._refresh_all_views(f, reset_page=False)

    def _on_page_size_changed(self, index: int) -> None:
        widget = self.sender()
        if widget:
            self._page_size = widget.itemData(index)
            self._page = 0
            f = self._carousel_filter or TaskFilter()
            self._refresh_all_views(f, reset_page=False)

    def _reset_pagination(self) -> None:
        self._page = 0

    def _auto_select_first(self) -> None:
        model = self._task_model
        if model.rowCount() > 0:
            first_task = model.tasks[0]
            model.set_highlighted_task(first_task.id)
            self._task_view.setCurrentIndex(model.index(0, 0))
            self._on_task_selected(first_task)

    # ------------------------------------------------------------------
    # Status bar helpers
    # ------------------------------------------------------------------

    def _update_status_bar(self, filter_: TaskFilter) -> None:
        counts = self._repository.get_status_counts(partition_id=self._active_partition_id)
        overdue = counts.get(TaskStatus.OVERDUE, 0)
        doing = counts.get(TaskStatus.DOING, 0)
        todo = counts.get(TaskStatus.TODO, 0)
        done = counts.get(TaskStatus.DONE, 0)
        total = sum(counts.values())
        preset = self._quick_overview._active_preset if hasattr(self._quick_overview, '_active_preset') else "all"
        motd = self._config.get("motd", preset, default=self._config.get("motd", "all", default=""))
        breakdown = f"逾期 {overdue} | 进行中 {doing} | 待办 {todo} | 已完成 {done} | 共{total}项"
        self._status_msg.setText(
            f"{breakdown} | {motd}" if motd else breakdown
        )

    def _flash_status(self, msg: str) -> None:
        self._status_msg.setText(msg)
        QTimer.singleShot(3000, lambda: self._status_msg.setText("就绪"))

    # ------------------------------------------------------------------
    # Partition management
    # ------------------------------------------------------------------

    def _load_partitions(self) -> None:
        partitions = self._repository.get_all_partitions()
        self._status_partition_menu.clear()
        name_map = self._repository.get_partition_name_map()
        current_pid = self._active_partition_id or ""
        for p in partitions:
            pid, pname = p["id"], p["name"]
            locked = "🔒" if self._partition_passwords.get(pid, "") else ""
            check = "✓ " if pid == current_pid else "  "
            action = self._status_partition_menu.addAction(
                f"{check}{locked} {pname}",
                lambda checked=False, i=pid: self._activate_partition(i),
            )
        self._update_partition_status_btn()
        if not self._active_partition_id:
            current = self._config.get("general", "last_partition_id", default="")
            if current:
                self._activate_partition(current)
            else:
                first = self._find_first_unlocked_partition()
                if first:
                    self._activate_partition(first)

    def _update_partition_status_btn(self) -> None:
        pid = self._active_partition_id or ""
        name_map = self._repository.get_partition_name_map()
        pname = name_map.get(pid, "")
        locked = "🔒" if self._partition_passwords.get(pid, "") else ""
        txt = f"📁 {locked}{pname}" if pname else "📁 切换分区"
        self._status_partition_btn.setText(txt)

    def _activate_partition(self, pid: str) -> None:
        if self._partition_passwords.get(self._active_partition_id or "", ""):
            self._splitter_stack.setCurrentIndex(1)
            return
        self._active_partition_id = pid or ""
        self._config.set("general", "last_partition_id", value=self._active_partition_id)
        self._config.save()
        if pid and self._partition_passwords.get(pid, ""):
            self._splitter_stack.setCurrentIndex(1)
        else:
            self._splitter_stack.setCurrentIndex(0)
        today = date.today()
        self._carousel_filter = TaskFilter()
        self._carousel_filter.date_from = today
        self._carousel_filter.date_to = today
        self._page = 0
        self._update_partition_status_btn()
        self._heatmap_widget.set_partition_id(pid or None)
        self._status_badge.set_partition_id(pid or None)
        self._progress_bar.set_partition_id(pid or None)
        self._quick_overview.set_partition_id(pid or None)
        self._on_data_changed()
        self._heatmap_widget.force_refresh()
        # Refresh analysis page if currently visible
        if self._current_view == "dashboard" and hasattr(self, '_analysis_task_tree'):
            d_from, d_to = getattr(self, '_analysis_date_range', (None, None))
            self._refresh_analysis()
            self._analysis_task_tree.refresh(d_from, d_to, self._active_partition_id)
        # Auto-open first task or show welcome page
        if self._task_model.rowCount() > 0:
            self._on_task_selected(self._task_model.tasks[0])
        else:
            self._edit_panel.show_empty()

    def _on_unlock_partition(self) -> None:
        pid = self._active_partition_id
        if not pid:
            return
        stored = self._partition_passwords.get(pid, "")
        if not stored:
            return
        pw, ok = QInputDialog.getText(self, "解锁分区", "请输入密码：", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if pw.strip() == stored:
            self._partition_passwords[pid] = ""
            self._splitter_stack.setCurrentIndex(0)
            self._load_partitions()
        else:
            QMessageBox.warning(self, "错误", "密码不正确")

    def _lock_partition(self, target_id: str) -> None:
        pw = self._partition_passwords.get(target_id, "")
        if pw:
            self._splitter_stack.setCurrentIndex(1)

    def _find_first_unlocked_partition(self) -> str | None:
        parts = self._repository.get_all_partitions()
        for p in parts:
            if not self._partition_passwords.get(p["id"], ""):
                return p["id"]
        return None

    def _on_partitions_changed(self) -> None:
        self._load_partitions()

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    def _switch_view(self, view: str) -> None:
        if view == self._current_view:
            return
        self._current_view = view
        # Cancel any pending deferred loads
        if hasattr(self, '_deferred_timer') and self._deferred_timer.isActive():
            self._deferred_timer.stop()

        if view == "edit":
            self._stack.setCurrentIndex(0)
            self._heatmap_widget.nav_bar.setVisible(False)
            self._top_bar.show()
        elif view == "dashboard":
            self._stack.setCurrentIndex(1)
            self._heatmap_widget.nav_bar.setVisible(True)
            self._top_bar.hide()
            self._deferred_timer = QTimer(self)
            self._deferred_timer.setSingleShot(True)
            self._deferred_timer.timeout.connect(self._load_dashboard_data)
            self._deferred_timer.start(0)
        elif view == "batch":
            self._stack.setCurrentIndex(2)
            self._heatmap_widget.nav_bar.setVisible(False)
            self._top_bar.hide()
            self._refresh_batch_page()

    def _load_dashboard_data(self) -> None:
        """Load dashboard stats after view switch (report loads on period click)."""
        self._refresh_analysis()

    # ------------------------------------------------------------------
    # Activity analysis slots
    # ------------------------------------------------------------------

    def _refresh_analysis(self) -> None:
        """Refresh analysis page: heatmap stats + task tree."""
        if hasattr(self, '_analysis_stats') and hasattr(self, '_heatmap_widget'):
            model = self._heatmap_widget._model
            self._analysis_stats.refresh(
                total=model.total_count(),
                active_days=model.active_days(),
                longest_streak=model.longest_streak(),
                daily_avg=model.daily_average(),
            )

    def _on_analysis_period_changed(self, d_from, d_to, label: str) -> None:
        """Period change → highlight heatmap + refresh task tree + select first task."""
        self._analysis_date_range = (d_from, d_to)
        if d_from is not None and d_to is not None:
            self._heatmap_widget.highlight_range(d_from, d_to, label)
        else:
            self._heatmap_widget.highlight_range(None, None, "")
        if hasattr(self, '_analysis_task_tree'):
            self._analysis_task_tree.refresh(d_from, d_to, self._active_partition_id)

    def _on_analysis_tag_selected(self, tag: str) -> None:
        """Tag selected → show flowing activity content for tasks in that tag."""
        if not tag or not hasattr(self, '_analysis_content_view'):
            if hasattr(self, '_analysis_content_view'):
                self._analysis_content_view.show_hint()
            return
        tasks = self._analysis_task_tree.get_tasks_for_tag(tag)
        d_from, d_to = getattr(self, '_analysis_date_range', (None, None))
        self._analysis_content_view.show_tag_activity(tag, tasks, d_from, d_to)

    def _on_content_scrolled_to_bottom(self) -> None:
        """Auto-advance to next checked tag when user scrolls to bottom of content."""
        if not hasattr(self, '_analysis_task_tree'):
            return
        current_tag = self._analysis_task_tree.get_active_tag()
        if not current_tag:
            return
        next_tag = self._analysis_task_tree.get_next_checked_tag(current_tag)
        if next_tag:
            self._analysis_task_tree.select_tag(next_tag)

    def _on_heatmap_date_clicked(self, d: date) -> None:
        """Handle date click on heatmap grid."""
        if hasattr(self, '_analysis_period_selector'):
            self._analysis_period_selector.set_custom_range(d, d)

    def _on_analysis_search_changed(self, text: str) -> None:
        """Filter activity content by search text."""
        if hasattr(self, '_analysis_content_view'):
            self._analysis_content_view.set_search_text(text)

    def _on_export_analysis_md(self) -> None:
        self._export_analysis("md")

    def _on_export_analysis_xlsx(self) -> None:
        self._export_analysis("xlsx")

    def _on_export_analysis_txt(self) -> None:
        self._export_analysis("txt")

    def _export_analysis(self, fmt: str) -> None:
        """Export analysis content for all checked tags to file."""
        d_from, d_to = getattr(self, '_analysis_date_range', (None, None))

        # Collect plain text from all checked tags
        texts: list[str] = []
        if hasattr(self, '_analysis_task_tree') and hasattr(self, '_analysis_content_view'):
            checked_tags = self._analysis_task_tree.get_checked_tags()
            for tag in checked_tags:
                tasks = self._analysis_task_tree.get_tasks_for_tag(tag)
                self._analysis_content_view.show_tag_activity(tag, tasks, d_from, d_to)
                t = self._analysis_content_view.get_plain_text()
                if t:
                    texts.append(t)
            # Restore current view
            current_tag = self._analysis_task_tree.get_active_tag()
            if current_tag:
                tasks = self._analysis_task_tree.get_tasks_for_tag(current_tag)
                self._analysis_content_view.show_tag_activity(current_tag, tasks, d_from, d_to)

        text = "\n".join(texts)
        if not text:
            return

        # Build default filename with tag count
        def_name = self._build_export_filename(fmt, len(checked_tags) if hasattr(self, '_analysis_task_tree') else 0)
        filters = {"md": "Markdown (*.md)", "xlsx": "Excel (*.xlsx)", "txt": "文本文件 (*.txt)"}
        filepath, _ = QFileDialog.getSaveFileName(self, "导出报告", def_name, filters.get(fmt, ""))
        if not filepath:
            return

        if fmt == "xlsx":
            self._export_xlsx_file(filepath, text)
        elif fmt == "md":
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)

    def _build_export_filename(self, fmt: str, tag_count: int = 0) -> str:
        """Build default export filename: 分区名_时间范围_n个标签.ext"""
        name_map = self._repository.get_partition_name_map()
        pname = name_map.get(self._active_partition_id or "", "默认分区")
        d_from, d_to = getattr(self, '_analysis_date_range', (None, None))
        date_str = ""
        if d_from and d_to:
            date_str = f"{d_from.isoformat()}" if d_from == d_to else f"{d_from.isoformat()}~{d_to.isoformat()}"
        tag_suffix = f"_{tag_count}个标签" if tag_count > 0 else ""
        return f"{pname}_{date_str}{tag_suffix}.{fmt}"

    def _export_xlsx_file(self, filepath: str, text: str = "") -> None:
        """Export as Excel with split columns: 序号, 任务, 状态变更, 进度变更, 活动信息."""
        try:
            import openpyxl
            from openpyxl.styles import Font, Alignment
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "活动报告"
            headers = ["序号", "任务", "状态变更", "进度变更", "活动信息"]
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=h)
                cell.font = Font(bold=True)
            rows = self._parse_export_rows(text)
            for r, row_data in enumerate(rows, 2):
                for c, val in enumerate(row_data, 1):
                    ws.cell(row=r, column=c, value=val)
            ws.column_dimensions['A'].width = 6
            ws.column_dimensions['B'].width = 30
            ws.column_dimensions['C'].width = 14
            ws.column_dimensions['D'].width = 12
            ws.column_dimensions['E'].width = 60
            wb.save(filepath)
        except ImportError:
            QMessageBox.warning(self, "错误", "需要安装 openpyxl 库才能导出 Excel")

    def _parse_export_rows(self, text: str) -> list[tuple]:
        """Parse plain text format into Excel rows.
        Format:
            #tag
            1. title [status, prog]:
                entry line 1
                entry line 2
        """
        rows = []
        current_num = ""
        current_title = ""
        current_status = ""
        current_prog = ""
        current_entries: list[str] = []

        def _flush():
            if current_num and current_entries:
                rows.append((
                    int(current_num), current_title, current_status,
                    current_prog, "\n".join(current_entries)
                ))

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Ordered list item: "1. title [status, prog]:"
            if stripped[0].isdigit() and ". " in stripped:
                _flush()
                current_entries = []
                parts = stripped.split(". ", 1)
                current_num = parts[0]
                rest = parts[1]
                if " [" in rest and "]:" in rest:
                    current_title = rest.split(" [", 1)[0]
                    bracket = rest.split("[", 1)[1].split("]", 1)[0]
                    if ", " in bracket:
                        current_status, current_prog = bracket.split(", ", 1)
                    else:
                        current_status, current_prog = bracket, ""
                else:
                    current_title = rest.rstrip(":")
            elif line.startswith("    ") and current_num:
                current_entries.append(stripped)

        _flush()
        return rows

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    def _on_new_task(self) -> None:
        self._on_new_draft()

    def _on_menu_new_draft(self) -> None:
        """Menu bar: show window, discard any draft silently, create new."""
        if self._edit_panel.has_unsaved_draft():
            self._edit_panel.discard_draft()
        self._ensure_window_ready()
        self._edit_panel.create_draft()
        self._apply_splitter_sizes()

    def _on_menu_new_multi(self) -> None:
        """Menu bar: show window, discard any draft silently, create multi."""
        if self._edit_panel.has_unsaved_draft():
            self._edit_panel.discard_draft()
        self._ensure_window_ready()
        self._edit_panel.create_draft_multi()
        self._apply_splitter_sizes()

    def _ensure_window_ready(self) -> None:
        """Show, raise, and switch to edit view. Updates _current_view so
        subsequent view switches work correctly."""
        self._current_view = "edit"
        self._top_bar.show()
        self._heatmap_widget.nav_bar.setVisible(False)
        if self._splitter_stack.currentIndex() == 1:
            if self._partition_passwords.get(self._active_partition_id, ""):
                self._on_unlock_partition()
            else:
                self._splitter_stack.setCurrentIndex(0)
        self._stack.setCurrentIndex(0)
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self._edit_panel.set_active_partition(self._active_partition_id)

    def _on_new_draft(self) -> None:
        # From tray (window hidden): silently discard draft, no popup
        if not self.isVisible() and self._edit_panel.has_unsaved_draft():
            self._edit_panel.discard_draft()
        elif not self._guard_draft():
            return
        if self._splitter_stack.currentIndex() == 1:
            if self._partition_passwords.get(self._active_partition_id, ""):
                self._on_unlock_partition()
                if self._splitter_stack.currentIndex() == 1:
                    return
            else:
                self._splitter_stack.setCurrentIndex(0)
        self._stack.setCurrentIndex(0)
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self._edit_panel.set_active_partition(self._active_partition_id)
        self._edit_panel.create_draft()
        self._apply_splitter_sizes()

    def _guard_draft(self) -> bool:
        if not self._edit_panel.has_unsaved_draft():
            return True
        msg = QMessageBox(self)
        msg.setWindowTitle("未保存的草稿")
        msg.setText("当前有未保存的新建任务，是否保存？")
        save_btn = msg.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg.addButton("放弃", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == save_btn:
            self._edit_panel._on_save()
            return True
        if clicked == discard_btn:
            self._edit_panel.discard_draft()
            return True
        return False

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Markdown", "", "Markdown 文件 (*.md *.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            from ..services.md_importer import MarkdownImporter
            count = MarkdownImporter(self._repository).import_file(path)
            self._on_data_changed()
            self._flash_status(f"已导入 {count} 个任务")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown", "tasks.md", "Markdown 文件 (*.md);;所有文件 (*)"
        )
        if not path:
            return
        try:
            from ..services.md_exporter import MarkdownExporter
            tasks = self._repository.get_all()
            MarkdownExporter.export_to_file(tasks, path)
            self._flash_status(f"已导出到 {path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self._config, self._repository, self)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self._signal_bus.config_changed.emit()

    def _on_about(self) -> None:
        dlg = AboutDialog(self)
        dlg.exec()

    def _on_help_docs(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("https://github.com/user/desktodoseq/wiki"))

    def _on_quit(self) -> None:
        self._signal_bus.application_quit.emit()

    def _on_refresh(self) -> None:
        self._quick_overview.refresh()
        self._on_data_changed()

    def _on_config_changed(self) -> None:
        self._filter_bar.set_sort(self._config.default_sort)
        self._on_data_changed()

    # ------------------------------------------------------------------
    # Midnight timer
    # ------------------------------------------------------------------

    def _setup_midnight_timer(self) -> None:
        self._midnight_timer = QTimer(self)
        self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight_crossed)
        self._schedule_midnight_timer()

    def _schedule_midnight_timer(self) -> None:
        now = QDateTime.currentDateTime()
        tomorrow = now.addDays(1)
        midnight = QDateTime(tomorrow.date(), QTime(0, 0, 1))
        ms = now.msecsTo(midnight)
        if ms <= 0:
            ms = 1000
        self._midnight_timer.start(ms)

    def _on_midnight_crossed(self) -> None:
        self._quick_overview.refresh()
        if self._current_view != "edit":
            self._refresh_report()
        self._on_data_changed()
        self._schedule_midnight_timer()
