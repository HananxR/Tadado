"""Main window — Todoseq-style layout with custom title bar and adaptive sizing."""

from __future__ import annotations

import ctypes
import datetime as dt
from ctypes import wintypes
from datetime import date

from PySide6.QtCore import QDateTime, QSize, Qt, QTime, QTimer
from PySide6.QtGui import (
    QAction, QBrush, QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap,
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
    QToolBar,
    QToolButton,
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
from .calendar_heatmap.activity_report_panel import ActivityReportPanel
from .calendar_heatmap.calendar_heatmap_widget import CalendarHeatmapWidget
from .calendar_heatmap.collapse_panel import HeatmapCollapsePanel
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
        self._heatmap_mode: str = "hidden"

        self.setWindowTitle("DeskTodoSeq")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self._setup_custom_title_bar()
        self._setup_tool_bar()
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

        self._title_menu_bar = QMenuBar()
        self._title_menu_bar.setNativeMenuBar(False)
        self._title_menu_bar.setFixedHeight(bar_h)
        file_menu = self._title_menu_bar.addMenu("文件(&F)")
        file_menu.addAction("新建任务(&N)\tCtrl+N", self._on_new_task)
        file_menu.addSeparator()
        file_menu.addAction("导入 Markdown...(&I)", self._on_import)
        file_menu.addAction("导出 Markdown...(&E)", self._on_export)
        file_menu.addSeparator()
        file_menu.addAction("退出(&Q)", self._on_quit)
        view_menu = self._title_menu_bar.addMenu("视图(&V)")
        view_menu.addAction("热度日历(&H)\tCtrl+H", self._on_toggle_heatmap)
        help_menu = self._title_menu_bar.addMenu("帮助(&H)")
        help_menu.addAction("设置(&S)", self._on_settings)
        help_menu.addAction("帮助文档(&D)", self._on_help_docs)
        help_menu.addSeparator()
        help_menu.addAction("关于(&A)", self._on_about)
        tb.addWidget(self._title_menu_bar)

        tb.addStretch()

        for kind, slot, tip, btn_name in [
            ("minimize", self.showMinimized, "最小化", "titleBtn"),
            ("maximize", self._toggle_maximize, "最大化", "titleBtn"),
            ("close",    self.close,             "关闭",   "closeBtn"),
        ]:
            btn = QPushButton()
            btn.setIcon(self._make_window_button_icon(kind))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(bar_h, bar_h)
            btn.setFlat(True)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            btn.setObjectName(btn_name)
            tb.addWidget(btn)
            if kind == "maximize":
                self._maximize_btn = btn

        self.setMenuWidget(title_bar)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _make_window_button_icon(self, kind: str) -> QIcon:
        from ..utils.design_tokens import get_tokens
        color = QColor(get_tokens().text_secondary)
        px = QPixmap(64, 64)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(color, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if kind == "minimize":
            p.drawLine(20, 32, 44, 32)
        elif kind == "maximize":
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(18, 18, 28, 28, 4, 4)
        elif kind == "close":
            p.drawLine(20, 20, 44, 44)
            p.drawLine(44, 20, 20, 44)
        p.end()
        return QIcon(px)

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
        if g.y() <= y < g.y() + 36:
            if x >= g.x() + g.width() - 108:
                return False, 0
            if x < g.x() + 36:
                return False, 0
            menu_w = self._title_menu_bar.width()
            if x < g.x() + 36 + menu_w:
                return False, 0
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

    @staticmethod
    def _make_partition_icon() -> QIcon:
        from ..utils.design_tokens import get_tokens
        px = QPixmap(64, 64)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(get_tokens().accent)
        p.setBrush(QBrush(color))
        p.setPen(QPen(color.darker(130), 2.5))
        r = 4
        tab_l, tab_t, tab_w, tab_h = 16, 14, 14, 8
        p.drawRoundedRect(tab_l, tab_t, tab_w, tab_h, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(tab_l, tab_t + tab_h - r, tab_w, r)
        p.setPen(QPen(color.darker(130), 2.5))
        body_l, body_t, body_w, body_h = 12, 20, 40, 28
        p.drawRoundedRect(body_l, body_t, body_w, body_h, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(tab_l, body_t, tab_w, r)
        p.end()
        return QIcon(px)

    def _setup_tool_bar(self) -> None:
        toolbar = QToolBar()
        toolbar.setWindowTitle("导航")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        # Partition selector — QToolButton + QMenu, matches "新建"/"视图" style
        self._partition_btn = QToolButton()
        self._partition_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._partition_btn.setIcon(self._make_partition_icon())
        self._partition_btn.setText("切换分区")
        self._partition_btn.setToolTip("切换分区")
        self._partition_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._partition_menu = QMenu(self._partition_btn)
        self._partition_btn.setMenu(self._partition_menu)
        self._partition_btn.clicked.connect(lambda: self._partition_btn.showMenu())
        toolbar.addWidget(self._partition_btn)
        self._partition_colors = ["#5b8def", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]

        toolbar.addSeparator()

        self._new_task_btn = QToolButton()
        self._new_task_btn.setObjectName("newTaskBtn")
        self._new_task_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._new_task_btn.setIcon(load_icon("new_task"))
        self._new_task_btn.setText("新建")
        self._new_task_btn.setToolTip("新建任务")
        self._new_task_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._new_task_btn.clicked.connect(self._on_new_draft)
        new_menu = QMenu(self._new_task_btn)
        single_action = new_menu.addAction("新增单任务")
        single_action.triggered.connect(self._on_new_draft)
        multi_action = new_menu.addAction("新增多任务")
        multi_action.triggered.connect(self._on_new_multi_task)
        self._new_task_btn.setMenu(new_menu)
        toolbar.addWidget(self._new_task_btn)

        toolbar.addSeparator()

        self._view_btn = QToolButton()
        self._view_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._view_btn.setIcon(load_icon("heatmap"))
        self._view_btn.setText("视图")
        self._view_btn.setToolTip("切换视图")
        self._view_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._view_btn.clicked.connect(self._on_toggle_heatmap)
        view_menu = QMenu(self._view_btn)
        view_menu.addAction("热度日历", self._on_toggle_heatmap)
        view_menu.addSeparator()
        self._view_btn.setMenu(view_menu)
        toolbar.addWidget(self._view_btn)

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
        self._heatmap_widget.back_requested.connect(lambda: self._set_heatmap_mode("hidden"))

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

        self._edit_panel = TaskEditPanel(self._repository, self._config)
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

        # === Page 1: Heatmap + Activity Report ===
        heatmap_page = QWidget()
        heatmap_layout = QVBoxLayout(heatmap_page)
        heatmap_layout.setContentsMargins(8, 4, 8, 4)
        heatmap_layout.setSpacing(4)

        heatmap_top = QWidget()
        heatmap_top_row = QHBoxLayout(heatmap_top)
        heatmap_top_row.setContentsMargins(0, 0, 0, 0)
        heatmap_top_row.addStretch()
        heatmap_top_row.addWidget(self._heatmap_widget.nav_bar)
        heatmap_top_row.addSpacing(4)
        heatmap_layout.addWidget(heatmap_top)

        collapsible = HeatmapCollapsePanel(self._heatmap_widget)
        heatmap_layout.addWidget(collapsible, 1)

        self._report_panel = ActivityReportPanel(self._repository)
        self._report_panel.setVisible(False)
        heatmap_layout.addWidget(self._report_panel)

        self._stack.addWidget(heatmap_page)
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
        self._status_bar = QStatusBar()
        self._status_bar.setSizeGripEnabled(True)
        # Left: partition icon + name :: stats + motd
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

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_task)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_refresh)
        QShortcut(QKeySequence("Ctrl+H"), self, activated=self._on_toggle_heatmap)
        QShortcut(QKeySequence("Escape"), self, activated=self._on_escape)

    # ------------------------------------------------------------------
    # Slots: data refresh
    # ------------------------------------------------------------------

    def _on_data_changed(self, *args) -> None:
        if hasattr(self, '_splitter_stack') and self._splitter_stack.currentIndex() == 1:
            return
        if hasattr(self, '_progress_bar'):
            self._progress_bar.reset_to_unclicked()
        f = self._carousel_filter or TaskFilter()
        self._refresh_all_views(f, reset_page=False)

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
        self._update_page_label()
        self._update_status_bar(filter_)
        self._status_badge.refresh(filter_.date_from, filter_.date_to)
        self._progress_bar.refresh()

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
        elif preset == "week":
            today = date.today()
            f.date_from = today - dt.timedelta(days=today.isoweekday() - 1)
            f.date_to = f.date_from + dt.timedelta(days=6)
        elif preset == "yesterday":
            yesterday = date.today() - dt.timedelta(days=1)
            f.date_from = yesterday
            f.date_to = yesterday
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
        if self._heatmap_mode != "hidden":
            self._refresh_report()
            self._heatmap_widget.highlight_range(f.date_from, f.date_to, preset)

    def _on_status_clicked(self, status: TaskStatus) -> None:
        f = TaskFilter(statuses=[status])
        if self._carousel_filter:
            f.tags = list(self._carousel_filter.tags)
        self._carousel_filter = f
        self._refresh_all_views(f)

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
        pass

    def _on_carousel_clicked(self, task_id: str) -> None:
        task = self._repository.get_by_id(task_id)
        if task:
            self._edit_panel.load_task(task)

    def _on_heatmap_data_changed(self, *args) -> None:
        if hasattr(self, '_heatmap_widget'):
            self._heatmap_widget.force_refresh()

    def _on_go_home(self) -> None:
        self._carousel_filter = None
        self._filter_bar.reset()
        self._on_data_changed()
        self._last_activity = dt.datetime.now()

    def _on_escape(self) -> None:
        if self._heatmap_mode != "hidden":
            self._set_heatmap_mode("hidden")
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
        total = self._total_count
        # Partition name
        name_map = self._repository.get_partition_name_map()
        pname = name_map.get(self._active_partition_id or "", "默认分区")
        # Motd
        preset = self._quick_overview._active_preset if hasattr(self._quick_overview, '_active_preset') else "all"
        motd = self._config.get("motd", preset, default=self._config.get("motd", "all", default=""))
        self._status_msg.setText(
            f"📁 {pname} :: 共 {total} 项 | {motd}"
        )

    def _flash_status(self, msg: str) -> None:
        self._status_msg.setText(msg)
        QTimer.singleShot(3000, lambda: self._status_msg.setText("就绪"))

    # ------------------------------------------------------------------
    # Partition management
    # ------------------------------------------------------------------

    def _load_partitions(self) -> None:
        partitions = self._repository.get_all_partitions()
        self._partition_menu.clear()
        for p in partitions:
            pid, pname = p["id"], p["name"]
            locked = "🔒" if self._partition_passwords.get(pid, "") else ""
            action = self._partition_menu.addAction(
                f"{locked} {pname}",
                lambda checked=False, i=pid: self._activate_partition(i),
            )
        # Update button text to current partition
        self._update_partition_btn_text()
        if not self._active_partition_id:
            current = self._config.get("general", "last_partition_id", default="")
            if current:
                self._activate_partition(current)
            else:
                first = self._find_first_unlocked_partition()
                if first:
                    self._activate_partition(first)

    def _update_partition_btn_text(self) -> None:
        pid = self._active_partition_id or ""
        name_map = self._repository.get_partition_name_map()
        pname = name_map.get(pid, "")
        locked = "🔒" if self._partition_passwords.get(pid, "") else ""
        self._partition_btn.setText(f"{locked} {pname}" if pname else "切换分区")

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
        self._carousel_filter = None
        self._page = 0
        self._update_partition_btn_text()
        self._heatmap_widget.set_partition_id(pid or None)
        self._on_data_changed()
        self._heatmap_widget.force_refresh()
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
    # Heatmap
    # ------------------------------------------------------------------

    def _set_heatmap_mode(self, mode: str) -> None:
        if mode == self._heatmap_mode:
            return
        self._heatmap_mode = mode
        if mode == "hidden":
            self._stack.setCurrentIndex(0)
            self._heatmap_widget.nav_bar.setVisible(False)
            self._top_bar.show()
            self._report_panel.setVisible(False)
        elif mode == "split":
            self._stack.setCurrentIndex(1)
            self._heatmap_widget.nav_bar.setVisible(True)
            self._top_bar.hide()
            self._report_panel.setVisible(True)
            self._refresh_report()

    def _on_toggle_heatmap(self) -> None:
        if self._heatmap_mode == "hidden":
            self._set_heatmap_mode("split")
        else:
            self._set_heatmap_mode("hidden")

    def _refresh_report(self) -> None:
        if self._carousel_filter:
            self._report_panel.refresh(
                self._carousel_filter.date_from,
                self._carousel_filter.date_to,
                self._active_partition_id,
                "",
            )

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    def _on_new_task(self) -> None:
        self._on_new_draft()

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
        if self._heatmap_mode != "hidden":
            self._refresh_report()
        self._on_data_changed()
        self._schedule_midnight_timer()
