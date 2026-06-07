"""Main window — Todoseq-style layout with custom title bar and adaptive sizing."""

from __future__ import annotations

import ctypes
import datetime as dt
from ctypes import wintypes
from datetime import date

from PySide6.QtCore import QDateTime, QEvent, QSize, Qt, QTime, QTimer
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
    QSizePolicy,
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
from .widgets.calendar_popup import CalendarPopup
from .widgets.dropdown import DropdownWidget
from .dialogs.about_dialog import AboutDialog
from .dialogs.settings_dialog import SettingsDialog
from .task_list.batch_toolbar import BatchToolbar
from .task_list.task_edit_panel import TaskEditPanel
from .task_list.task_list_model import COL_ARCHIVED, TaskListModel
from .task_list.task_list_view import TaskListView
from .widgets.filter_bar import FilterBar
from .widgets.progress_dynamics_bar import ProgressDynamicsBar
from .widgets.quick_overview_bar import QuickOverviewBar
from .widgets.status_badge_strip import StatusBadgeStrip
from .widgets.tag_management_panel import TagManagementPanel


class MainWindow(QMainWindow):
    """Desktop task manager with Markdown-first workflow."""

    def __init__(self, config: AppConfig, repository: TaskRepository) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        # ── DWM pre-config: must run BEFORE show(), right after HWND creation ──
        # Force native HWND creation so DWM attributes can be set immediately,
        # before DWM ever composites a single frame for this window.
        self.winId()
        from ..utils.win32_theme import (
            set_window_nc_rendering_disabled,
            set_window_cloaked,
        )
        set_window_nc_rendering_disabled(self)   # never draw native NC buttons
        set_window_cloaked(self, True)           # hide from DWM until fully ready
        # ──────────────────────────────────────────────────────────────────────

        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._config = config
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._carousel_filter: TaskFilter | None = None
        self._active_partition_id: str | None = None
        self._partition_passwords: dict[str, str] = {}
        self._partition_auto_lock: dict[str, int] = {}
        self._page: int = 0
        self._page_size: int = config.get("general", "page_size", default=20)
        self._total_count: int = 0
        self._current_view: str = "edit"
        self._analysis_date_range: tuple = (None, None)
        self._selection_guard: bool = False  # prevents signal recursion from selectRow()
        self._new_task_sort_active: bool = False  # True after task creation, reset on user nav
        self._setting_sort_internally: bool = False  # guard against self-triggered filter change

        self.setWindowTitle("Tadado")

        self._setup_custom_title_bar()
        self._setup_status_bar()
        self._setup_central_widget()
        self._setup_idle_lock()
        self._connect_signals()
        self._setup_shortcuts()
        self._setup_midnight_timer()
        self._load_partitions()
        self._apply_splitter_sizes()

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
        self._apply_batch_splitter_sizes()
        self._sync_header_alignment()

    def _apply_splitter_sizes(self) -> None:
        if self._splitter is None:
            return
        total = self._splitter.width()
        if total > 100:
            self._splitter.setSizes([int(total * 0.50), int(total * 0.50)])

    def _apply_batch_splitter_sizes(self) -> None:
        """Set batch page splitter to 70:30 (existing content : tag panel)."""
        if not hasattr(self, '_batch_splitter') or self._batch_splitter is None:
            return
        total = self._batch_splitter.width()
        if total > 100:
            self._batch_splitter.setSizes([int(total * 0.80), int(total * 0.20)])

    def _sync_header_alignment(self) -> None:
        """Sync editor header height to match table header for vertical alignment."""
        hh = self._task_view.horizontalHeader()
        if hh:
            h = hh.height()
            if h > 0:
                self._edit_panel.set_header_height(h)

    def refresh_theme(self) -> None:
        self._edit_panel.refresh_theme()
        if hasattr(self, '_analysis_content_view'):
            self._analysis_content_view.refresh_theme()

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

        # Nav buttons (icon + text, flat style) — colors via base.qss
        btn_style = (
            "QPushButton { border: none; background: transparent; padding: 2px 8px; font-size: 11px; }"
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
            btn.setObjectName("titleBtn")
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

        # Right-side window buttons (icon only) — colors via base.qss
        right_btn_style = (
            "QPushButton { border: none; background: transparent; padding: 0px; }"
        )
        right_items = [
            ("tray_hide", "缩小到托盘", self.hide),
            ("window_minimize", "最小化", self._on_minimize),
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
            # Right-side window buttons area (4 * 36px icon buttons)
            if x >= g.x() + g.width() - 144:
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

    def _on_minimize(self) -> None:
        """Minimize button — respects *minimize_to_tray* config.

        When enabled, hide directly to tray (no taskbar flash).
        Otherwise do a normal minimize to the taskbar.
        """
        if self._config.minimize_to_tray:
            self.hide()
        else:
            self.showMinimized()

    def changeEvent(self, event) -> None:
        """Intercept minimize: hide to tray when *minimize_to_tray* is enabled."""
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.windowState() & Qt.WindowState.WindowMinimized
        ):
            if self._config.minimize_to_tray:
                self.hide()
                event.ignore()
                return
        super().changeEvent(event)

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
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 1)

        # === Left panel: BatchToolbar + TaskListView + Pagination ===
        left_panel = QWidget()
        left_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 2, 0)
        left_layout.setSpacing(2)

        self._batch_toolbar = BatchToolbar()
        left_layout.addWidget(self._batch_toolbar)

        self._task_model = TaskListModel()
        self._task_view = TaskListView(self._repository)
        self._task_view.set_model(self._task_model)
        self._task_view.setColumnHidden(COL_ARCHIVED, True)  # 归档列仅管理视图可见
        self._task_view.task_selected.connect(self._on_view_task_selected)
        self._task_view.detail_requested.connect(self._on_detail_requested)
        # Batch operations from right-click menu
        self._task_view.batch_status_change.connect(self._on_batch_status_change)
        self._task_view.batch_urgency_change.connect(self._on_batch_urgency_change)
        self._task_view.batch_delete.connect(self._on_batch_delete)
        self._task_view.batch_suspend.connect(self._on_batch_suspend)
        self._task_view.batch_restart.connect(self._on_batch_restart)
        self._task_view.batch_postpone.connect(self._on_batch_postpone)
        self._task_view.batch_move_partition.connect(self._on_batch_move_partition)
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
        self._page_size_combo = DropdownWidget()
        self._page_size_combo.setFixedWidth(combo_width(4))
        for n in ["20", "50", "100"]:
            self._page_size_combo.addItem(n, int(n))
        self._page_size_combo.setCurrentText(str(self._page_size))
        self._page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        page_row.addWidget(self._page_size_combo)
        left_layout.addWidget(page_widget)

        self._splitter.addWidget(left_panel)

        # === Right panel: ProgressDynamicsBar + TaskEditPanel ===
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
        # ── Section: Heatmap ──
        heatmap_label = QLabel("活动热力图")
        heatmap_label.setObjectName("analysisSectionLabel")
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
        report_label.setObjectName("analysisSectionLabel")
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

        export_btn = QPushButton("导出")
        export_btn.setObjectName("exportBtn")
        export_btn.setFixedHeight(28)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self._analysis_content_view.prev_requested.connect(self._on_analysis_prev)
        self._analysis_content_view.next_requested.connect(self._on_analysis_next)
        self._analysis_splitter.addWidget(self._analysis_content_view)

        self._analysis_splitter.setStretchFactor(0, 1)  # ~25%
        self._analysis_splitter.setStretchFactor(1, 3)  # ~75%
        analysis_layout.addWidget(self._analysis_splitter, 1)

        # Connect heatmap grid signals
        self._heatmap_widget.grid.date_clicked.connect(self._on_heatmap_date_clicked)

        self._stack.addWidget(analysis_page)

        # === Page 2: Task Management Console ===
        from ..utils.design_tokens import get_tokens as _gt4

        batch_page = QWidget()
        batch_page_layout = QHBoxLayout(batch_page)
        batch_page_layout.setContentsMargins(0, 0, 0, 0)
        batch_page_layout.setSpacing(0)

        # -- Left sidebar (180px) --
        self._manage_sidebar = QWidget()
        self._manage_sidebar.setObjectName("manageSidebar")
        self._manage_sidebar.setFixedWidth(180)
        sidebar_layout = QVBoxLayout(self._manage_sidebar)
        sidebar_layout.setContentsMargins(8, 6, 8, 6)
        sidebar_layout.setSpacing(3)

        SIDEBAR_LABEL = "font-size: 10px; font-weight: bold; border: none; padding-top: 4px;"
        SIDEBAR_INPUT = "font-size: 10px; padding: 2px 4px;"
        SIDEBAR_BTN = "QPushButton { font-size: 10px; padding: 4px 8px; }"

        def _add_sep():
            s = QWidget(); s.setObjectName("sidebarSep"); s.setFixedHeight(1)
            sidebar_layout.addWidget(s)

        def _add_label(text: str):
            lb = QLabel(text); lb.setStyleSheet(SIDEBAR_LABEL); sidebar_layout.addWidget(lb)

        def _add_date_row(placeholder: str) -> QLineEdit:
            """Return a date QLineEdit wrapped in a row with a clear button."""
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            le.setStyleSheet(SIDEBAR_INPUT)
            le.setReadOnly(True)
            le.mousePressEvent = lambda e, le_=le: self._open_date_popup(le_)
            row_layout.addWidget(le, 1)
            clear_btn = QPushButton("×")
            clear_btn.setFixedSize(16, 16)
            clear_btn.setObjectName("sidebarClearBtn")
            clear_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 0; border: none; }")
            clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            clear_btn.clicked.connect(lambda _, le_=le: (le_.clear(), self._on_batch_filter_changed()))
            row_layout.addWidget(clear_btn)
            sidebar_layout.addWidget(row)
            return le

        # ---- 筛选 ----
        _add_label("🔍 筛选")

        _add_label("关键词")
        self._batch_search = QLineEdit()
        self._batch_search.setPlaceholderText("搜索...")
        self._batch_search.setStyleSheet(SIDEBAR_INPUT)
        self._batch_search_timer = QTimer(self)
        self._batch_search_timer.setSingleShot(True)
        self._batch_search_timer.timeout.connect(self._on_batch_search)
        self._batch_search.textChanged.connect(lambda: self._batch_search_timer.start(300))
        sidebar_layout.addWidget(self._batch_search)

        _add_label("状态")
        self._batch_status_combo = DropdownWidget()
        self._batch_status_combo.addItem("全部", None)
        for s in (TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE, TaskStatus.OVERDUE):
            self._batch_status_combo.addItem(s.display_name, s)
        self._batch_status_combo.currentIndexChanged.connect(self._on_batch_filter_changed)
        sidebar_layout.addWidget(self._batch_status_combo)

        _add_label("优先级")
        self._batch_priority_combo = DropdownWidget()
        self._batch_priority_combo.addItem("全部", None)
        _BATCH_URGENCY_LABELS = [(0, "● 紧急"), (1, "● 重要"), (2, "● 关注"), (3, "● 普通")]
        for val, label in _BATCH_URGENCY_LABELS:
            self._batch_priority_combo.addItem(label, val)
        self._batch_priority_combo.currentIndexChanged.connect(self._on_batch_filter_changed)
        sidebar_layout.addWidget(self._batch_priority_combo)

        _add_label("创建时间")
        self._batch_created_from = _add_date_row("起始日期")
        self._batch_created_to = _add_date_row("结束日期")

        _add_label("截止时间")
        self._batch_deadline_from = _add_date_row("起始日期")
        self._batch_deadline_to = _add_date_row("结束日期")

        _add_label("进度")
        self._batch_progress_combo = DropdownWidget()
        self._batch_progress_combo.addItem("全部", (0, 100))
        for label, rng in [("0%", (0, 0)), ("1-25%", (1, 25)), ("26-50%", (26, 50)),
                            ("51-75%", (51, 75)), ("100%", (100, 100))]:
            self._batch_progress_combo.addItem(label, rng)
        self._batch_progress_combo.currentIndexChanged.connect(self._on_batch_filter_changed)
        sidebar_layout.addWidget(self._batch_progress_combo)

        _add_label("标签")
        self._batch_tag_input = QLineEdit()
        self._batch_tag_input.setPlaceholderText("#标签1 #标签2")
        self._batch_tag_input.setStyleSheet(SIDEBAR_INPUT)
        self._batch_tag_timer = QTimer(self)
        self._batch_tag_timer.setSingleShot(True)
        self._batch_tag_timer.timeout.connect(self._on_batch_filter_changed)
        self._batch_tag_input.textChanged.connect(lambda: self._batch_tag_timer.start(300))
        sidebar_layout.addWidget(self._batch_tag_input)

        _add_label("归档状态")
        self._batch_archive_combo = DropdownWidget()
        self._batch_archive_combo.addItem("全部", "all")
        self._batch_archive_combo.addItem("未归档", "unarchived")
        self._batch_archive_combo.addItem("已归档", "archived")
        self._batch_archive_combo.currentIndexChanged.connect(self._on_batch_filter_changed)
        sidebar_layout.addWidget(self._batch_archive_combo)

        # ---- 分隔 + 操作 ----
        _add_sep()
        _add_label("🛠 操作")

        self._archive_btn = QPushButton("归档已完成")
        self._archive_btn.setStyleSheet(SIDEBAR_BTN)
        self._archive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._archive_btn.clicked.connect(self._on_manual_archive)
        sidebar_layout.addWidget(self._archive_btn)

        self._clear_archived_btn = QPushButton("清除已归档")
        self._clear_archived_btn.setStyleSheet(SIDEBAR_BTN)
        self._clear_archived_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_archived_btn.clicked.connect(self._on_clear_archived)
        sidebar_layout.addWidget(self._clear_archived_btn)

        sidebar_layout.addStretch()

        back_btn2 = QPushButton()
        back_btn2.setIcon(load_icon("home"))
        back_btn2.setIconSize(QSize(16, 16))
        back_btn2.setFixedSize(24, 24)
        back_btn2.setFlat(True)
        back_btn2.setToolTip("返回主界面")
        back_btn2.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn2.setObjectName("sidebarHomeBtn")
        back_btn2.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; }"
        )
        back_btn2.clicked.connect(lambda: self._switch_view("edit"))
        sidebar_layout.addWidget(back_btn2, alignment=Qt.AlignmentFlag.AlignHCenter)

        # -- Main content area --
        batch_main = QWidget()
        batch_layout = QVBoxLayout(batch_main)
        batch_layout.setContentsMargins(8, 4, 8, 4)
        batch_layout.setSpacing(4)

        # Operation toolbar
        self._batch_toolbar2 = BatchToolbar()
        self._batch_toolbar2.select_all_requested.connect(self._on_batch_select_all)
        self._batch_toolbar2.deselect_all_requested.connect(self._on_batch_deselect_all)
        self._batch_toolbar2.export_requested.connect(self._on_batch_export)
        batch_layout.addWidget(self._batch_toolbar2)

        # Task table (full width, no edit panel)
        self._batch_task_model = TaskListModel()
        self._batch_task_view = TaskListView(self._repository)
        self._batch_task_view.set_model(self._batch_task_model)
        self._batch_task_view.setSelectionBehavior(
            self._batch_task_view.SelectionBehavior.SelectRows
        )
        self._batch_task_view.task_selected.connect(self._on_batch_task_selected)
        self._batch_task_view.batch_status_change.connect(self._on_batch_status_change)
        self._batch_task_view.batch_urgency_change.connect(self._on_batch_urgency_change)
        self._batch_task_view.batch_delete.connect(self._on_batch_delete)
        self._batch_task_view.batch_suspend.connect(self._on_batch_suspend)
        self._batch_task_view.batch_restart.connect(self._on_batch_restart)
        self._batch_task_view.batch_postpone.connect(self._on_batch_postpone)
        self._batch_task_view.batch_move_partition.connect(self._on_batch_move_partition)
        self._batch_task_model.dataChanged.connect(self._on_batch_model_data_changed)
        batch_layout.addWidget(self._batch_task_view, 1)

        # Pagination row (matching main pagination style)
        self._batch_page_size = self._config.get("general", "page_size", default=20)
        batch_pager = QWidget()
        batch_pager_layout = QHBoxLayout(batch_pager)
        batch_pager_layout.setContentsMargins(4, 2, 4, 2)
        batch_pager_layout.setSpacing(4)
        batch_pager_layout.addStretch()
        self._batch_prev_btn = QPushButton("‹")
        self._batch_prev_btn.setObjectName("navBtn")
        self._batch_prev_btn.setFixedWidth(28)
        self._batch_prev_btn.clicked.connect(self._on_batch_page_prev)
        batch_pager_layout.addWidget(self._batch_prev_btn)
        self._batch_page_label = QLabel("1 / 1")
        self._batch_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        batch_pager_layout.addWidget(self._batch_page_label)
        self._batch_next_btn = QPushButton("›")
        self._batch_next_btn.setObjectName("navBtn")
        self._batch_next_btn.setFixedWidth(28)
        self._batch_next_btn.clicked.connect(self._on_batch_page_next)
        batch_pager_layout.addWidget(self._batch_next_btn)
        self._batch_page_size_combo = DropdownWidget()
        self._batch_page_size_combo.setFixedWidth(combo_width(4))
        for n in ["20", "50", "100"]:
            self._batch_page_size_combo.addItem(n, int(n))
        self._batch_page_size_combo.setCurrentText(str(self._batch_page_size))
        self._batch_page_size_combo.currentIndexChanged.connect(self._on_batch_page_size_changed)
        batch_pager_layout.addWidget(self._batch_page_size_combo)
        batch_layout.addWidget(batch_pager)

        # Confirm bar (hidden by default)
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

        # === Batch splitter: existing content (70%) + tag panel (30%) ===
        self._batch_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._batch_splitter.setHandleWidth(2)
        self._batch_splitter.setChildrenCollapsible(False)

        batch_left = QWidget()
        batch_left_layout = QHBoxLayout(batch_left)
        batch_left_layout.setContentsMargins(0, 0, 0, 0)
        batch_left_layout.setSpacing(0)
        batch_left_layout.addWidget(self._manage_sidebar)
        batch_left_layout.addWidget(batch_main, 1)
        self._batch_splitter.addWidget(batch_left)

        self._batch_tag_panel = TagManagementPanel(self._repository, config=self._config)
        self._batch_splitter.addWidget(self._batch_tag_panel)
        self._batch_splitter.setStretchFactor(0, 1)
        self._batch_splitter.setStretchFactor(1, 0)

        batch_page_layout.addWidget(self._batch_splitter)
        self._stack.addWidget(batch_page)
        self._batch_page = 0
        self._batch_total_count = 0
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
        self._status_partition_btn = QPushButton("● 切换分区")
        self._status_partition_btn.setFlat(True)
        self._status_partition_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 解析 accent 色为 RGB 分量，用 rgba 保证背景可见
        accent = t.accent if t else "#5b8def"
        r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
        self._status_partition_btn.setStyleSheet(
            f"QPushButton {{ border: none; border-left: 3px solid {accent}; "
            f"background: rgba({r},{g},{b},0.15); border-radius: 4px; "
            f"padding: 2px 8px 2px 6px; font-size: 11px; "
            f"font-weight: bold; color: {accent}; }}"
            f"QPushButton:hover {{ background: rgba({r},{g},{b},0.25); }}"
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
        mins = self._partition_auto_lock.get(self._active_partition_id or "", 3)
        if not mins or mins <= 0:
            return
        if self._splitter_stack.currentIndex() == 1:
            return
        if self._last_activity is None:
            self._last_activity = dt.datetime.now()
            return
        elapsed = (dt.datetime.now() - self._last_activity).total_seconds() / 60.0
        if elapsed >= mins / 2.0:
            pid = self._active_partition_id or ""
            has_pw, stored = self._repository.check_partition_password(pid)
            if has_pw:
                self._partition_passwords[pid] = stored  # 从 DB 恢复密码
                self._idle_timer.stop()
                self._lock_partition(pid)

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

        # Tag management
        self._batch_tag_panel.tag_changed.connect(lambda: bus.tag_changed.emit())
        bus.tag_changed.connect(self._on_data_changed)
        bus.task_created.connect(lambda *_: self._batch_tag_panel.refresh())
        bus.task_updated.connect(lambda *_: self._batch_tag_panel.refresh())
        bus.task_deleted.connect(lambda *_: self._batch_tag_panel.refresh())

        bus.task_created.connect(self._on_heatmap_data_changed)
        bus.task_updated.connect(self._on_heatmap_data_changed)
        bus.task_deleted.connect(self._on_heatmap_data_changed)
        bus.task_status_changed.connect(self._on_heatmap_data_changed)
        bus.batch_operation_completed.connect(self._on_heatmap_data_changed)

        self._task_model.dataChanged.connect(self._on_model_data_changed)

        self._batch_toolbar.select_all_requested.connect(self._on_edit_select_all)
        self._batch_toolbar.deselect_all_requested.connect(self._on_edit_deselect_all)
        self._batch_toolbar.export_requested.connect(self._on_batch_export)

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
        f = self._build_filter_with_sort()
        self._refresh_all_views(f, reset_page=False)
        if _sizes:
            self._splitter.setSizes(_sizes)
        # Re-select task if triggered by a task update signal (keep current task open)
        if args and hasattr(args[0], 'id'):
            self._select_and_load_task(args[0].id)

    def _on_tasks_bulk_created(self, count: int, task_ids: list) -> None:
        """Handle multi-task creation: switch to creation-time sort, refresh, highlight first."""
        self._new_task_sort_active = True
        self._filter_bar.blockSignals(True)
        self._filter_bar.set_sort("created")
        self._filter_bar.reset()
        self._filter_bar._debounce.stop()  # 杀死 reset() 残留的 300ms debounce，避免竞态
        self._filter_bar.blockSignals(False)
        if hasattr(self, '_quick_overview') and self._quick_overview.active_preset != "today":
            self._new_task_sort_active = False  # 临时清除，避免 _on_quick_preset 恢复默认排序
            self._quick_overview.activate_preset("today")
            self._new_task_sort_active = True
        self._on_data_changed()
        if self._task_model.tasks:
            self._on_task_selected(self._task_model.tasks[0])

    def _build_filter_with_sort(self) -> TaskFilter:
        """Build filter with FilterBar's sort as base, overlay scope from carousel/partition."""
        f = self._filter_bar.build_filter()  # preserves sort + search + status
        if self._carousel_filter is not None:
            f.date_from = self._carousel_filter.date_from
            f.date_to = self._carousel_filter.date_to
            f.partition_id = self._carousel_filter.partition_id or self._active_partition_id or None  # "" → None
        else:
            f.partition_id = self._active_partition_id or None  # "" → None
        return f

    def _refresh_all_views(self, filter_: TaskFilter, reset_page: bool = True) -> None:
        if reset_page:
            self._reset_pagination()
        filter_.partition_id = filter_.partition_id or self._active_partition_id or None  # "" → None
        all_tasks = self._repository.search(filter_)
        self._total_count = self._repository.count(filter_)
        # Paginate table display — full list still passed to overview / progress bar
        start = self._page * self._page_size
        page_tasks = all_tasks[start:start + self._page_size]
        self._task_model.set_offset(start)
        self._task_model.load_tasks(page_tasks)
        self._quick_overview.set_items(all_tasks)
        self._update_page_label()
        self._update_status_bar(filter_)
        self._status_badge.refresh(filter_.date_from, filter_.date_to)
        self._progress_bar.set_items(all_tasks)

    def _on_task_created(self, task) -> None:
        self._new_task_sort_active = True
        self._filter_bar.blockSignals(True)
        self._filter_bar.set_sort("created")
        self._filter_bar.reset()
        self._filter_bar._debounce.stop()  # 杀死 reset() 残留的 300ms debounce，避免竞态
        self._filter_bar.blockSignals(False)
        if hasattr(self, '_quick_overview') and self._quick_overview.active_preset != "today":
            self._new_task_sort_active = False  # 临时清除，避免 _on_quick_preset 恢复默认排序
            self._quick_overview.activate_preset("today")
            self._new_task_sort_active = True
        self._on_data_changed()
        self._on_task_selected(task)

    def _select_and_load_task(self, task_id: str) -> None:
        """Find task by ID and delegate to _on_task_selected (unified凸显 entry)."""
        for row in range(self._task_model.rowCount()):
            if self._task_model.tasks[row].id == task_id:
                self._on_task_selected(self._task_model.tasks[row])
                return

    def _on_task_deleted(self, task_id: str) -> None:
        self._on_data_changed()

    def _on_batch_completed(self) -> None:
        self._on_data_changed()

    # ------------------------------------------------------------------
    # Batch page methods
    # ------------------------------------------------------------------

    def _refresh_batch_page(self) -> None:
        """Refresh the task management page applying all sidebar filters."""
        if not hasattr(self, '_batch_task_model'):
            return
        f = TaskFilter()
        f.sort_by = self._filter_bar.build_filter().sort_by  # inherit main sort
        f.partition_id = self._active_partition_id
        f.search_text = self._batch_search.text().strip()
        # Status
        sd = self._batch_status_combo.currentData()
        if sd is not None:
            f.statuses = {sd}
        # Priority / Urgency
        pd = self._batch_priority_combo.currentData()
        if pd is not None:
            f.urgencies = {pd}
        # Created time
        f.created_from = self._read_date_edit('_batch_created_from')
        f.created_to = self._read_date_edit('_batch_created_to')
        # Deadline time
        f.date_from = self._read_date_edit('_batch_deadline_from')
        f.date_to = self._read_date_edit('_batch_deadline_to')
        # Progress
        lo, hi = self._batch_progress_combo.currentData()
        f.progress_min = lo
        f.progress_max = hi
        # Tags (strip leading # for consistency with UI display format)
        tag_text = self._batch_tag_input.text().strip()
        if tag_text:
            f.tags = set(t.strip().lstrip("#").strip() for t in tag_text.split() if t.strip())
        # Archive status
        arc = self._batch_archive_combo.currentData()
        if arc == "all" or arc == "archived":
            f.show_archived = True

        if arc == "archived":
            # Load all tasks (no limit), filter client-side, then paginate manually
            f.limit = None
            f.offset = 0
            tasks = [t for t in self._repository.search(f) if t.archived]
            self._batch_total_count = len(tasks)
            start = self._batch_page * self._batch_page_size
            tasks = tasks[start:start + self._batch_page_size]
        else:
            f.limit = self._batch_page_size
            f.offset = self._batch_page * self._batch_page_size
            tasks = self._repository.search(f)
            self._batch_total_count = self._repository.count(f)
        self._batch_task_model.set_offset(self._batch_page * self._batch_page_size)
        self._batch_task_model.load_tasks(tasks)
        self._update_batch_pagination()

    def _read_date_edit(self, attr: str) -> date | None:
        """Parse yyyy-MM-dd from a QLineEdit attribute, return date or None."""
        le = getattr(self, attr, None)
        if le is None:
            return None
        txt = le.text().strip()
        if not txt:
            return None
        try:
            return date.fromisoformat(txt)
        except ValueError:
            return None

    def _open_date_popup(self, line_edit: QLineEdit) -> None:
        """Open CalendarPopup and set result into the QLineEdit."""
        txt = line_edit.text().strip()
        initial = date.fromisoformat(txt) if txt else date.today()
        popup = CalendarPopup(initial, self)
        popup.date_selected.connect(lambda qd: (
            line_edit.setText(qd.toPython().isoformat()),
            self._on_batch_filter_changed()
        ))
        popup.smart_place(line_edit)
        popup.exec()

    def _update_batch_pagination(self) -> None:
        if self._batch_page_size <= 0:
            self._batch_page_label.setText("全部")
            return
        total_pages = max(1, (self._batch_total_count + self._batch_page_size - 1) // self._batch_page_size)
        self._batch_page_label.setText(f"{self._batch_page + 1} / {total_pages}")
        self._batch_prev_btn.setEnabled(self._batch_page > 0)
        self._batch_next_btn.setEnabled(self._batch_page < total_pages - 1)

    def _on_batch_search(self) -> None:
        self._batch_page = 0
        self._refresh_batch_page()

    def _on_batch_filter_changed(self) -> None:
        self._batch_page = 0
        self._refresh_batch_page()

    def _on_batch_page_prev(self) -> None:
        if self._batch_page > 0:
            self._batch_page -= 1
            self._refresh_batch_page()
            if hasattr(self, '_batch_task_model') and self._batch_task_model.rowCount() > 0:
                self._batch_task_model.set_highlighted_task(
                    self._batch_task_model.tasks[0].id)

    def _on_batch_page_next(self) -> None:
        total_pages = max(1, (self._batch_total_count + self._batch_page_size - 1) // self._batch_page_size)
        if self._batch_page < total_pages - 1:
            self._batch_page += 1
            self._refresh_batch_page()
            if hasattr(self, '_batch_task_model') and self._batch_task_model.rowCount() > 0:
                self._batch_task_model.set_highlighted_task(
                    self._batch_task_model.tasks[0].id)

    def _on_batch_page_size_changed(self, index: int) -> None:
        widget = self.sender()
        if widget:
            self._batch_page_size = widget.itemData(index)
            self._batch_page = 0
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

    def _on_batch_task_selected(self, task: Task) -> None:
        """Highlight the selected task in the batch view."""
        self._batch_task_model.set_highlighted_task(task.id)

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
                self._task_model.set_checked_ids(set())
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
                self._flash_status(f"已更改 {len(ids)} 个任务状态")
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
        self._flash_status(f"已更改 {len(action['ids'])} 个任务状态")

    def _on_batch_urgency_change(self, ids: list[str], urgency: int) -> None:
        """Handle batch urgency change from toolbar."""
        self._repository.batch_update_urgency(ids, urgency)
        if self._current_view == "batch":
            self._batch_task_model.deselect_all()
            self._batch_toolbar2.reset_toggle()
            self._refresh_batch_page()
        else:
            self._task_model.set_checked_ids(set())
            self._batch_toolbar.reset_toggle()
            current = self._edit_panel.current_task()
            if current and current.id in ids:
                updated = self._repository.get_by_id(current.id)
                if updated:
                    self._edit_panel.load_task(updated)
        self._on_data_changed()
        self._flash_status(f"已更改 {len(ids)} 个任务优先级")

    def _on_batch_delete(self, ids: list[str]) -> None:
        if self._current_view == "edit":
            reply = QMessageBox.question(
                self, "确认删除",
                f"确认删除 {len(ids)} 个任务？此操作不可撤销。",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self._repository.batch_delete(ids)
                self._task_model.set_checked_ids(set())
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
                self._flash_status(f"已删除 {len(ids)} 个任务")
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
        self._flash_status(f"已删除 {len(action['ids'])} 个任务")

    def _on_batch_suspend(self, ids: list[str]) -> None:
        if self._current_view == "edit":
            reply = QMessageBox.question(
                self, "确认操作",
                f"确认中止 {len(ids)} 个任务？",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self._repository.batch_suspend(ids)
                self._task_model.set_checked_ids(set())
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
                self._flash_status(f"已中止 {len(ids)} 个任务")
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
        self._flash_status(f"已中止 {len(action['ids'])} 个任务")

    def _on_batch_restart(self, ids: list[str]) -> None:
        if self._current_view == "edit":
            reply = QMessageBox.question(
                self, "确认操作",
                f"确认重启 {len(ids)} 个任务？",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Ok:
                self._repository.batch_restart(ids)
                self._task_model.set_checked_ids(set())
                self._on_data_changed()
                self._batch_toolbar.reset_toggle()
                self._flash_status(f"已重启 {len(ids)} 个任务")
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
        self._flash_status(f"已重启 {len(action['ids'])} 个任务")

    def _on_batch_postpone(self, ids: list[str], days: int) -> None:
        reply = QMessageBox.question(
            self, "确认操作",
            f"确认将 {len(ids)} 个任务的截止时间延后 {days} 天？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self._repository.batch_postpone(ids, days)
            if self._current_view == "edit":
                self._task_model.set_checked_ids(set())
                self._batch_toolbar.reset_toggle()
            else:
                self._refresh_batch_page()
            self._on_data_changed()
            self._flash_status(f"已延后 {len(ids)} 个任务")

    def _on_batch_move_partition(self, ids: list[str]) -> None:
        """Move selected tasks to a different partition with password checks."""
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QVBoxLayout, QDialogButtonBox

        from_partition_id = self._active_partition_id or ""
        name_map = self._repository.get_partition_name_map()
        from_name = name_map.get(from_partition_id, "未分配") if from_partition_id else "未分配"

        # ── Step 1: Verify FROM partition password ──
        from_pw = self._partition_passwords.get(from_partition_id, "")
        if from_pw:
            pw, ok = QInputDialog.getText(
                self, "验证来源分区密码",
                f"来源分区「{from_name}」设有密码，请输入密码：",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            if pw.strip() != from_pw:
                QMessageBox.warning(self, "错误", "密码不正确")
                return

        # ── Step 2: Select target partition ──
        partitions = self._repository.get_all_partitions()
        # Exclude current partition
        other = [p for p in partitions if p["id"] != from_partition_id]
        if not other:
            QMessageBox.information(self, "提示", "没有其他分区可供迁移。")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("选择目标分区")
        dlg.resize(320, 240)
        layout = QVBoxLayout(dlg)

        list_widget = QListWidget(dlg)
        for p in other:
            pid, pname = p["id"], p["name"]
            has_pw = bool(self._partition_passwords.get(pid, ""))
            label = f"{'🔒 ' if has_pw else ''}{pname}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            list_widget.addItem(item)
        list_widget.setCurrentRow(0)
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        selected = list_widget.currentItem()
        if selected is None:
            return
        to_partition_id = selected.data(Qt.ItemDataRole.UserRole)
        to_name = name_map.get(to_partition_id, to_partition_id)

        # ── Step 3: Verify TO partition password ──
        to_pw = self._partition_passwords.get(to_partition_id, "")
        if to_pw:
            pw, ok = QInputDialog.getText(
                self, "验证目标分区密码",
                f"目标分区「{to_name}」设有密码，请输入密码：",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            if pw.strip() != to_pw:
                QMessageBox.warning(self, "错误", "密码不正确")
                return

        # ── Step 4: Confirmation ──
        reply = QMessageBox.question(
            self, "确认操作",
            f"确认将 {len(ids)} 个任务从「{from_name}」移动到「{to_name}」？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return

        # ── Step 5: Execute ──
        moved = self._repository.batch_move_partition(ids, to_partition_id)
        if self._current_view == "edit":
            self._task_model.set_checked_ids(set())
            self._batch_toolbar.reset_toggle()
        else:
            self._refresh_batch_page()
        self._on_data_changed()
        self._flash_status(f"已将 {moved} 个任务移动至「{to_name}」")

    def _hide_confirm(self) -> None:
        self._confirm_bar.setVisible(False)
        self._batch_pending_action = {}

    # ------------------------------------------------------------------
    # Manual archive & clear
    # ------------------------------------------------------------------

    def _on_manual_archive(self) -> None:
        """Archive all DONE tasks in current partition (ignore archive_days threshold)."""
        pid = self._active_partition_id
        if not pid:
            return
        f = TaskFilter()
        f.sort_by = self._filter_bar.build_filter().sort_by
        f.partition_id = pid
        f.statuses = {TaskStatus.DONE}
        done_tasks = self._repository.search(f)
        if not done_tasks:
            QMessageBox.information(self, "归档", "当前分区没有已完成的任务。")
            return
        reply = QMessageBox.question(
            self, "确认归档",
            f"归档当前分区全部 {len(done_tasks)} 个已完成任务？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            ids = [t.id for t in done_tasks if not t.archived]
            if ids:
                self._repository.archive_batch(ids)
            self._batch_page = 0
            self._refresh_batch_page()
            self._on_data_changed()
            self._flash_status(f"已归档 {len(ids)} 个任务")

    def _on_clear_archived(self) -> None:
        """Permanently delete all archived tasks in current partition."""
        pid = self._active_partition_id
        if not pid:
            return
        f = TaskFilter()
        f.partition_id = pid
        f.show_archived = True
        all_tasks = self._repository.search(f)
        archived = [t for t in all_tasks if t.archived]
        if not archived:
            QMessageBox.information(self, "清除", "当前分区没有已归档的任务。")
            return
        reply = QMessageBox.warning(
            self, "⚠ 确认清除",
            f"将永久删除 {len(archived)} 个已归档任务，此操作不可恢复！",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            ids = [t.id for t in archived]
            self._repository.batch_delete(ids)
            self._batch_page = 0
            self._refresh_batch_page()
            self._on_data_changed()
            self._flash_status(f"已清除 {len(ids)} 个已归档任务")

    # ------------------------------------------------------------------
    # Batch export
    # ------------------------------------------------------------------

    def _on_batch_export(self, fmt: str) -> None:
        """Export all tasks in current partition to MD or Excel."""
        pid = self._active_partition_id
        f = TaskFilter()
        f.sort_by = self._filter_bar.build_filter().sort_by
        f.partition_id = pid
        tasks = self._repository.search(f)
        if not tasks:
            QMessageBox.information(self, "导出", "当前分区没有任务。")
            return

        name_map = self._repository.get_partition_name_map()
        pname = name_map.get(pid or "", "未知")
        today = date.today().isoformat()

        if fmt == "md":
            path, _ = QFileDialog.getSaveFileName(
                self, "导出 Markdown", f"{pname}_{today}.md",
                "Markdown 文件 (*.md);;所有文件 (*)"
            )
            if path:
                lines = [t.raw_md for t in tasks]
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(lines) + "\n")
                self._flash_status(f"已导出 {len(tasks)} 个任务到 {path}")
        elif fmt == "xlsx":
            path, _ = QFileDialog.getSaveFileName(
                self, "导出 Excel", f"{pname}_{today}.xlsx",
                "Excel 文件 (*.xlsx);;所有文件 (*)"
            )
            if path:
                from openpyxl import Workbook
                wb = Workbook()
                ws = wb.active
                ws.title = pname
                ws.append(["序号", "任务内容", "状态", "进度", "截止日期", "标签", "创建时间", "归档"])
                for i, t in enumerate(tasks, 1):
                    ws.append([
                        i, t.title, t.status.display_name, f"{t.progress}%",
                        t.deadline_date.isoformat() if t.deadline_date else "",
                        " ".join(f"#{tag}" for tag in t.tags),
                        t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
                        "已归档" if t.archived else ("未归档" if t.status == TaskStatus.DONE else "/"),
                    ])
                wb.save(path)
                self._flash_status(f"已导出 {len(tasks)} 个任务到 {path}")

    def _on_filter_changed(self, filter_: TaskFilter) -> None:
        if self._setting_sort_internally:
            pass  # internal set_sort() call — keep new_task_sort_active
        elif self._new_task_sort_active:
            self._new_task_sort_active = False
            self._setting_sort_internally = True
            self._filter_bar.set_sort(self._config.default_sort)
            self._setting_sort_internally = False
            return  # set_sort triggers another _on_filter_changed with default
        self._carousel_filter = filter_
        self._refresh_all_views(filter_)

    def _on_quick_preset(self, preset: str) -> None:
        if self._new_task_sort_active:
            self._new_task_sort_active = False
            self._setting_sort_internally = True
            self._filter_bar.set_sort(self._config.default_sort)
            self._setting_sort_internally = False
        f = self._filter_bar.build_filter()  # preserve sort
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
        if hasattr(self, '_task_model') and self._task_model.rowCount() > 0:
            self._on_task_selected(self._task_model.tasks[0])
        if self._current_view != "edit":
            self._heatmap_widget.highlight_range(f.date_from, f.date_to, preset)

    def _on_status_clicked(self, status: TaskStatus) -> None:
        f = self._filter_bar.build_filter()
        f.statuses = [status] if status else None
        if self._carousel_filter:
            f.tags = list(self._carousel_filter.tags)
        self._carousel_filter = f
        self._refresh_all_views(f)

    def _on_progress_filter(self, filter_: TaskFilter) -> None:
        self._carousel_filter = filter_
        self._refresh_all_views(filter_)
        if self._task_model.tasks:
            self._on_task_selected(self._task_model.tasks[0])

    def _on_view_task_selected(self, task: Task) -> None:
        """Guard against signal recursion from selectRow() inside _on_task_selected."""
        if self._selection_guard:
            return
        self._on_task_selected(task)

    def _on_task_selected(self, task: Task) -> None:
        """统一任务凸显入口：模型凸显 + 编辑器加载 + 视图定位滚动。"""
        self._task_model.set_highlighted_task(task.id)
        self._edit_panel.load_task(task)
        self._last_activity = dt.datetime.now()
        # 在列表中定位并滚动到该任务
        for row in range(self._task_model.rowCount()):
            if self._task_model.tasks[row].id == task.id:
                self._selection_guard = True
                self._task_view.selectRow(row)
                self._task_view.scrollTo(self._task_model.index(row, 0))
                self._selection_guard = False
                break

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
        # Always switch to edit view first
        if self._current_view != "edit":
            self._switch_view("edit")
        # Ensure quick overview is on "today" preset
        if hasattr(self, '_quick_overview') and self._quick_overview.active_preset != "today":
            self._quick_overview.activate_preset("today")
        # Reset filters and select first task
        self._carousel_filter = None
        self._filter_bar.reset()
        self._page = 0
        self._refresh_all_views(self._build_filter_with_sort(), reset_page=True)
        if hasattr(self, '_task_model') and self._task_model.rowCount() > 0:
            self._on_task_selected(self._task_model.tasks[0])
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
            self._refresh_all_views(self._build_filter_with_sort(), reset_page=False)
            if self._task_model.rowCount() > 0:
                self._on_task_selected(self._task_model.tasks[0])

    def _on_page_next(self) -> None:
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        if self._page < total_pages - 1:
            self._page += 1
            self._refresh_all_views(self._build_filter_with_sort(), reset_page=False)
            if self._task_model.rowCount() > 0:
                self._on_task_selected(self._task_model.tasks[0])

    def _on_page_size_changed(self, index: int) -> None:
        widget = self.sender()
        if widget:
            self._page_size = widget.itemData(index)
            self._page = 0
            self._refresh_all_views(self._build_filter_with_sort(), reset_page=False)

    def _reset_pagination(self) -> None:
        self._page = 0

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
        self._in_load_partitions = True
        default_pid = self._repository.ensure_default_partition()  # 无分区时自动创建"功能演示"分区
        # 持久化默认分区到 config（首次创建 / 旧 UUID 指向已删除分区时自动修复）
        current_default = self._config.get("general", "default_partition", default="")
        name_map = self._repository.get_partition_name_map()
        if not current_default or not name_map.get(current_default):
            self._config.set("general", "default_partition", value=default_pid)
            self._config.save()
        partitions = self._repository.get_all_partitions()
        # 同步密码 + auto_lock 到内存
        for p in partitions:
            pid = p["id"]
            db_pw = p.get("password", "")
            if db_pw:
                if pid not in self._partition_passwords:
                    self._partition_passwords[pid] = db_pw
                elif self._partition_passwords[pid]:
                    self._partition_passwords[pid] = db_pw
            else:
                self._partition_passwords.pop(pid, None)
            self._partition_auto_lock[pid] = p.get("auto_lock_minutes", 3)
        self._status_partition_menu.clear()
        name_map = self._repository.get_partition_name_map()
        current_pid = self._active_partition_id or ""
        for p in partitions:
            pid, pname = p["id"], p["name"]
            db_pw = p.get("password", "")
            if db_pw:
                locked = "🔓 " if self._partition_passwords.get(pid, "") == "" else "🔒 "
            else:
                locked = ""
            check = "✓ " if pid == current_pid else "  "
            action = self._status_partition_menu.addAction(
                f"{check}{locked}{pname}",
                lambda checked=False, i=pid: self._activate_partition(i),
            )
        self._update_partition_status_btn()
        # 若当前激活的分区已被删除，重置使其落入激活链
        if self._active_partition_id and not self._repository.get_partition_name_map().get(
            self._active_partition_id
        ):
            self._active_partition_id = None
        if not self._active_partition_id:
            # 激活优先级：默认分区 > 上次使用的分区 > 第一个未锁定分区
            activated = False
            for key in ("default_partition", "last_partition_id"):
                pid = self._config.get("general", key, default="")
                if pid and self._repository.get_partition_name_map().get(pid):
                    self._activate_partition(pid)
                    activated = True
                    break
            if not activated:
                first = self._find_first_unlocked_partition()
                if first:
                    self._activate_partition(first)
        self._in_load_partitions = False

    def _update_partition_status_btn(self) -> None:
        pid = self._active_partition_id or ""
        name_map = self._repository.get_partition_name_map()
        pname = name_map.get(pid, "")
        has_pw, _ = self._repository.check_partition_password(pid) if pid else (False, "")
        if has_pw:
            locked = "🔓" if self._partition_passwords.get(pid, "") == "" else "🔒"
        else:
            locked = ""
        if pname:
            prefix = locked if locked else "●"
            txt = f"{prefix} {pname}"
        else:
            txt = "● 切换分区"
        self._status_partition_btn.setText(txt)

    def _activate_partition(self, pid: str) -> None:
        # 切换分区时立即恢复上一分区的密码（使其回归锁定状态）
        prev = self._active_partition_id
        if prev and prev != pid:
            has_pw, stored = self._repository.check_partition_password(prev)
            if has_pw:
                self._partition_passwords[prev] = stored

        self._active_partition_id = pid or ""
        self._config.set("general", "last_partition_id", value=self._active_partition_id)
        self._config.save()
        if pid and self._partition_passwords.get(pid, ""):
            self._splitter_stack.setCurrentIndex(1)
        else:
            self._splitter_stack.setCurrentIndex(0)
        self._carousel_filter = self._quick_overview.build_filter()
        self._page = 0
        self._update_partition_status_btn()
        self._heatmap_widget.set_partition_id(pid or None)
        self._status_badge.set_partition_id(pid or None)
        self._progress_bar.set_partition_id(pid or None)
        self._quick_overview.set_partition_id(pid or None)
        self._batch_tag_panel.set_partition_id(pid or "")
        if hasattr(self, '_batch_task_model'):
            self._refresh_batch_page()
        self._on_data_changed()
        # 刷新分区菜单 ✓ 标记（_load_partitions 递归调用时跳过）
        if not getattr(self, '_in_load_partitions', False):
            self._load_partitions()
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
            self._edit_panel.set_active_partition(self._active_partition_id)
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
        has_pw, stored = self._repository.check_partition_password(target_id)
        if has_pw:
            self._partition_passwords[target_id] = stored
            self._splitter_stack.setCurrentIndex(1)
            self._update_partition_status_btn()

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
            self._apply_splitter_sizes()
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
            if hasattr(self, '_batch_search'):
                self._batch_search.clear()
            self._batch_page = 0
            self._apply_batch_splitter_sizes()
            self._refresh_batch_page()

        # Reset filter bar sort to config default on view switch
        self._new_task_sort_active = False
        self._filter_bar.set_sort(self._config.default_sort)

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
        if not tag or not hasattr(self, '_analysis_content_view'):
            if hasattr(self, '_analysis_content_view'):
                self._analysis_content_view.show_hint()
            return
        tasks = self._analysis_task_tree.get_tasks_for_tag(tag)
        d_from, d_to = getattr(self, '_analysis_date_range', (None, None))
        checked = self._analysis_task_tree.get_checked_tags()
        if tag in checked:
            pos = checked.index(tag) + 1
        else:
            pos = 0
        self._analysis_content_view.set_current_tag(tag, pos, len(checked))
        self._analysis_content_view.show_tag_activity(tag, tasks, d_from, d_to)

    def _on_analysis_prev(self) -> None:
        if hasattr(self, '_analysis_task_tree'):
            self._analysis_task_tree.select_prev()

    def _on_analysis_next(self) -> None:
        if hasattr(self, '_analysis_task_tree'):
            self._analysis_task_tree.select_next()

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
        self._edit_panel.create_draft_single()
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
            self._load_partitions()  # 同步分区密码、auto_lock 等 DB → 内存
            # 设置保存后强制激活默认分区，确保状态栏与设置一致
            default_pid = self._config.get("general", "default_partition", default="")
            if default_pid and default_pid != (self._active_partition_id or ""):
                self._activate_partition(default_pid)
            self._signal_bus.config_changed.emit()

    def _on_about(self) -> None:
        dlg = AboutDialog(self)
        dlg.exec()

    def _on_help_docs(self) -> None:
        import sys
        from pathlib import Path
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        base = getattr(sys, "_MEIPASS", None)
        if base:
            path = Path(base) / "resources" / "help" / "manual.html"
        else:
            path = Path(__file__).resolve().parents[2] / "resources" / "help" / "manual.html"
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_quit(self) -> None:
        self._signal_bus.application_quit.emit()

    def _on_refresh(self) -> None:
        self._quick_overview.refresh()
        self._on_data_changed()

    def _on_config_changed(self) -> None:
        self._filter_bar.set_sort(self._config.default_sort)
        if hasattr(self, '_status_badge'):
            self._status_badge.refresh_theme()

        # Re-read page_size from config and sync all pagination controls
        new_page_size = self._config.get("general", "page_size", default=20)
        if self._page_size != new_page_size:
            self._page_size = new_page_size
            self._page = 0
            if hasattr(self, '_page_size_combo'):
                self._page_size_combo.setCurrentText(str(new_page_size))
        if self._batch_page_size != new_page_size:
            self._batch_page_size = new_page_size
            self._batch_page = 0
            if hasattr(self, '_batch_page_size_combo'):
                self._batch_page_size_combo.setCurrentText(str(new_page_size))
        if hasattr(self, '_batch_tag_panel'):
            self._batch_tag_panel.set_page_size(new_page_size)
            self._batch_tag_panel.refresh_theme()

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
