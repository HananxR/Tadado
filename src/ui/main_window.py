"""Main window — Todoseq-style layout with stats bar, carousel, and adaptive sizing."""

from __future__ import annotations

import datetime as dt
from datetime import date

from PySide6.QtCore import QDateTime, QSize, Qt, QTime, QTimer
from PySide6.QtGui import (
    QAction, QBrush, QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap,
    QShortcut, QKeySequence,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
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
from ..models.task_filter import TaskFilter
from ..models.task_status import TaskStatus
from ..services.md_formatter import MarkdownTaskFormatter
from ..services.md_parser import MarkdownTaskParser
from ..utils.icon_loader import load_icon
from ..utils.signal_bus import get_signal_bus
from .calendar_heatmap.calendar_heatmap_widget import CalendarHeatmapWidget
from .dialogs.about_dialog import AboutDialog
from .dialogs.settings_dialog import SettingsDialog
from .task_list.task_edit_panel import TaskEditPanel
from .task_list.task_list_model import TaskListModel
from .task_list.task_list_view import TaskListView
from .widgets.carousel_banner import CarouselBanner
from .widgets.filter_bar import FilterBar
from .widgets.status_stats_bar import StatusStatsBar


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

        self.setWindowTitle("DeskTodoSeq")

        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_status_bar()
        self._setup_central_widget()
        self._setup_idle_lock()
        self._connect_signals()
        self._setup_shortcuts()
        self._setup_midnight_timer()

    # ------------------------------------------------------------------
    # Adaptive sizing — called from app.py before show()
    # ------------------------------------------------------------------

    def apply_screen_size(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1050, 680)
            return
        geom = screen.availableGeometry()
        w = min(int(geom.width() * 0.82), geom.width() - 40)
        h = min(int(geom.height() * 0.80), geom.height() - 80)
        self.setMinimumSize(900, 600)
        self.resize(w, h)
        self.move(
            (geom.width() - w) // 2 + geom.x(),
            (geom.height() - h) // 2 + geom.y(),
        )

    def resizeEvent(self, event) -> None:
        """Re-apply splitter proportions on window resize."""
        super().resizeEvent(event)
        self._apply_splitter_sizes()

    def _apply_splitter_sizes(self) -> None:
        """Lock splitter to 65/35 proportion based on current width."""
        if self._splitter is None:
            return
        total = self._splitter.width()
        if total > 100:
            self._splitter.setSizes([int(total * 0.65), int(total * 0.35)])

    def refresh_theme(self) -> None:
        """Refresh theme-dependent styles after a theme switch."""
        self._edit_panel.refresh_theme()

    # ------------------------------------------------------------------
    # Menu bar — all actions live here
    # ------------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # --- File ---
        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction(load_icon("new_task"), "新建任务(&N)\tCtrl+N", self._on_new_task)
        file_menu.addSeparator()
        file_menu.addAction(load_icon("import"), "导入 Markdown...(&I)", self._on_import)
        file_menu.addAction(load_icon("export"), "导出 Markdown...(&E)", self._on_export)
        file_menu.addSeparator()
        file_menu.addAction("退出(&Q)", self._on_quit)

        # --- View ---
        view_menu = menu_bar.addMenu("视图(&V)")
        view_menu.addAction(load_icon("refresh"), "刷新(&R)\tCtrl+R", self._on_refresh)
        view_menu.addSeparator()
        view_menu.addAction(load_icon("heatmap"), "热力图(&H)\tCtrl+H", self._on_toggle_heatmap)

        # --- Help ---
        help_menu = menu_bar.addMenu("帮助(&H)")
        help_menu.addAction(load_icon("settings"), "设置(&S)", self._on_settings)
        help_menu.addSeparator()
        help_menu.addAction("关于(&A)", self._on_about)

    # ------------------------------------------------------------------
    # Tool bar — minimal: just the logo / home button
    # ------------------------------------------------------------------

    @staticmethod
    def _make_partition_icon() -> QIcon:
        """Draw a bookmark icon to represent partition switching."""
        from ..utils.design_tokens import get_tokens
        px = QPixmap(64, 64)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(get_tokens().accent)
        p.setBrush(QBrush(color))
        p.setPen(QPen(color.darker(130), 2.5))
        # Bookmark shape: rounded top rect + triangular bottom
        top = 10
        left = 18
        w = 28
        h_body = 34
        r = 4
        # Main body (rounded top corners only)
        p.drawRoundedRect(left, top, w, h_body, r, r)
        # Triangular bottom (V-shape)
        mid_x = left + w / 2
        bottom_y = top + h_body + 10
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        triangle = QPolygonF([
            QPointF(left, top + h_body),
            QPointF(mid_x, bottom_y),
            QPointF(left + w, top + h_body),
        ])
        p.drawPolygon(triangle)
        # Cover the bottom rounded corners of the rect with the triangle fill
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(left, top + h_body - r, w, r)
        p.end()
        return QIcon(px)

    def _setup_tool_bar(self) -> None:
        toolbar = QToolBar("导航")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)

        # Logo button — click returns to main task view
        logo_action = QAction(load_icon("app"), "DeskTodoSeq", self)
        logo_action.setToolTip("返回主界面")
        logo_action.triggered.connect(self._on_go_home)
        toolbar.addAction(logo_action)

        # Partition selector — icon-only with popup menu
        self._partition_btn = QToolButton()
        self._partition_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._partition_btn.setIcon(self._make_partition_icon())
        self._partition_btn.setToolTip("切换分区")
        self._partition_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._partition_menu = QMenu(self._partition_btn)
        self._partition_btn.setMenu(self._partition_menu)
        self._partition_btn.setStyleSheet(
            "QToolButton { border: none; padding: 4px 10px; }"
        )
        toolbar.addWidget(self._partition_btn)

        toolbar.addSeparator()

        # New-task button — creates a draft under "今日" filter
        new_action = QAction(load_icon("new_task"), "新建", self)
        new_action.setToolTip("在今日视角下新建任务")
        new_action.triggered.connect(self._on_new_draft)
        toolbar.addAction(new_action)

        toolbar.addAction(load_icon("refresh"), "刷新", self._on_refresh)
        toolbar.addAction(load_icon("heatmap"), "热力图", self._on_toggle_heatmap)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        self._stack = QStackedWidget()

        # === Page 0: Task view ===
        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(10, 6, 10, 6)
        task_layout.setSpacing(4)

        # Row 1: Carousel + preset filters in one distinct zone
        quick_zone = QWidget()
        quick_zone.setObjectName("quickZone")
        quick_row = QHBoxLayout(quick_zone)
        quick_row.setContentsMargins(10, 4, 10, 4)
        quick_row.setSpacing(12)

        self._carousel = CarouselBanner(max_items=10, group_size=3, interval_seconds=5)
        self._carousel.task_clicked.connect(self._on_carousel_clicked)
        quick_row.addWidget(self._carousel, 1)

        for label, preset in [
            ("全部", "all"), ("今日", "today"), ("本周", "week"), ("逾期", "overdue")
        ]:
            btn = QPushButton(label)
            btn.setFixedWidth(50)
            btn.setProperty("preset", True)
            btn.clicked.connect(lambda checked=False, p=preset: self._on_preset_filter(p))
            quick_row.addWidget(btn)

        task_layout.addWidget(quick_zone)

        # Row 3: Filter bar
        self._filter_bar = FilterBar()
        self._filter_bar.set_sort(self._config.default_sort)
        task_layout.addWidget(self._filter_bar)

        # Row 4: Status statistics bar
        self._stats_bar = StatusStatsBar(self._repository)
        self._stats_bar.filter_changed.connect(self._on_stats_filter)
        task_layout.addWidget(self._stats_bar)

        # Row 5: Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setObjectName("toolSeparator")
        task_layout.addWidget(sep)

        # Row 6: Splitter with password mask overlay
        from PySide6.QtWidgets import QStackedLayout as _QStackedLayout
        self._splitter_container = QWidget()
        self._splitter_stack = _QStackedLayout(self._splitter_container)
        self._splitter_stack.setContentsMargins(0, 0, 0, 0)
        self._splitter_stack.setStackingMode(_QStackedLayout.StackingMode.StackOne)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(False)

        # Password mask overlay (hidden by default)
        self._partition_mask = QWidget()
        self._partition_mask.setObjectName("partitionMask")
        mask_layout = QVBoxLayout(self._partition_mask)
        mask_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mask_hint = QLabel("🔒 此分区已加密\n请输入密码查看内容")
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
        self._splitter_stack.setCurrentIndex(0)

        self._splitter_stack.addWidget(self._splitter)
        self._splitter_stack.addWidget(self._partition_mask)

        # Left: task list
        self._task_model = TaskListModel()
        self._task_view = TaskListView(self._repository)
        self._task_view.set_model(self._task_model)
        self._task_view.setMinimumWidth(240)
        self._task_view.task_selected.connect(self._on_task_selected)
        self._task_view.detail_requested.connect(self._on_detail_requested)
        self._splitter.addWidget(self._task_view)

        # Right: edit panel
        self._edit_panel = TaskEditPanel(self._repository, self._task_model)
        self._splitter.addWidget(self._edit_panel)

        task_layout.addWidget(self._splitter_container, 1)

        # Pagination bar
        page_row = QHBoxLayout()
        page_row.setSpacing(6)

        self._page_prev_btn = QPushButton("◀")
        self._page_prev_btn.setFixedWidth(32)
        self._page_prev_btn.setStyleSheet("font-size: 10px;")
        self._page_prev_btn.clicked.connect(self._on_page_prev)
        page_row.addWidget(self._page_prev_btn)

        self._page_label = QLabel("0 / 0")
        self._page_label.setStyleSheet("font-size: 11px;")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedWidth(50)
        page_row.addWidget(self._page_label)

        self._page_next_btn = QPushButton("▶")
        self._page_next_btn.setFixedWidth(32)
        self._page_next_btn.setStyleSheet("font-size: 10px;")
        self._page_next_btn.clicked.connect(self._on_page_next)
        page_row.addWidget(self._page_next_btn)

        page_row.addSpacing(8)
        page_row.addWidget(QLabel("每页"))
        self._page_size_combo = QComboBox()
        self._page_size_combo.addItems(["10", "20", "50"])
        self._page_size_combo.setCurrentText(str(self._page_size))
        self._page_size_combo.setFixedWidth(50)
        self._page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        page_row.addWidget(self._page_size_combo)
        page_row.addStretch()
        task_layout.addLayout(page_row)

        self._stack.addWidget(task_page)

        # === Page 1: Calendar heatmap ===
        heatmap_page = QWidget()
        heatmap_layout = QVBoxLayout(heatmap_page)
        heatmap_layout.setContentsMargins(0, 0, 0, 0)

        # Center the heatmap horizontally
        h_center = QHBoxLayout()
        h_center.addStretch()
        self._heatmap_widget = CalendarHeatmapWidget(self._repository, self._config)
        self._heatmap_widget.setMaximumWidth(900)
        self._heatmap_widget.date_selected.connect(self._on_date_selected)
        h_center.addWidget(self._heatmap_widget)
        h_center.addStretch()

        heatmap_layout.addLayout(h_center)
        heatmap_layout.addStretch()
        self._stack.addWidget(heatmap_page)

        self._carousel_filter = TaskFilter()
        self._carousel.set_items([])
        # Load partitions into filter bar and edit panel
        self._load_partitions()

        self.setCentralWidget(self._stack)
        if self._splitter_stack.currentIndex() != 1:
            self._refresh_task_list()
            self._update_carousel(self._carousel_filter)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self._status_partition = QLabel()
        self._status_bar.addWidget(self._status_partition)
        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(
            QWidget().sizePolicy().horizontalPolicy().Expanding,
            QWidget().sizePolicy().verticalPolicy().Fixed,
        )
        self._status_bar.addWidget(spacer)
        self._status_clock = QLabel()
        self._status_bar.addPermanentWidget(self._status_clock)
        # Clock update timer
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()
        self.setStatusBar(self._status_bar)

    def _update_clock(self) -> None:
        from datetime import datetime as _dt
        self._status_clock.setText(_dt.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._status_clock.setStyleSheet("font-size: 11px; padding: 0 8px;")

    def _setup_idle_lock(self) -> None:
        """Set up auto-lock timer for password-protected partitions."""
        self._idle_lock_timer = QTimer(self)
        self._idle_lock_timer.setSingleShot(True)
        self._idle_lock_timer.timeout.connect(self._on_idle_lock)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Reset idle timer on user interaction."""
        from PySide6.QtCore import QEvent
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.KeyPress,
                            QEvent.Type.MouseButtonPress):
            self._reset_idle_lock_timer()
        return super().eventFilter(obj, event)

    def _reset_idle_lock_timer(self) -> None:
        """Reset the auto-lock countdown."""
        if not hasattr(self, '_idle_lock_timer'):
            return
        if not self._active_partition_id:
            return
        if not self._partition_passwords.get(self._active_partition_id, ""):
            return  # no password set for this partition
        if self._splitter_stack.currentIndex() == 1:
            return  # already locked
        timeout_min = self._config.get("general", "auto_lock_minutes", default=10)
        self._idle_lock_timer.start(timeout_min * 60 * 1000)

    def _on_idle_lock(self) -> None:
        """Auto-lock the current partition after idle timeout."""
        if not self._active_partition_id:
            return
        if not self._partition_passwords.get(self._active_partition_id, ""):
            return
        self._task_model.load_tasks([])
        self._edit_panel.clear()
        self._splitter_stack.setCurrentIndex(1)
        self._carousel.set_items([])
        for status in (TaskStatus.OVERDUE, TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            badge = self._stats_bar._badges.get(status)
            if badge:
                badge.setText(f"{badge.text().split(':')[0]}: 0")
        self._update_status_partition_label()

    # ------------------------------------------------------------------
    # Signals & shortcuts
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        bus = self._signal_bus
        bus.scan_completed.connect(self._on_data_changed)
        bus.task_created.connect(self._on_task_created)
        bus.task_updated.connect(self._on_data_changed)
        bus.task_deleted.connect(self._on_task_deleted)
        bus.task_status_changed.connect(self._on_data_changed)
        self._filter_bar.filter_changed.connect(self._on_filter_changed)
        bus.partitions_changed.connect(self._on_partitions_changed)
        bus.config_changed.connect(self._on_config_changed)
        bus.archive_completed.connect(self._on_data_changed)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_task)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_refresh)
        QShortcut(QKeySequence("Ctrl+H"), self, activated=self._on_toggle_heatmap)
        QShortcut(QKeySequence("Escape"), self, activated=self._edit_panel.clear)

    # ------------------------------------------------------------------
    # Slots: data refresh
    # ------------------------------------------------------------------

    def _on_data_changed(self, *args) -> None:
        if hasattr(self, '_splitter_stack') and self._splitter_stack.currentIndex() == 1:
            return  # partition locked, no data refresh
        f = self._carousel_filter or TaskFilter()
        self._refresh_all_views(f, reset_page=False)

    def _refresh_all_views(self, filter_: TaskFilter, reset_page: bool = True) -> None:
        """Single entry point: refresh task list, stats, carousel, and status bar."""
        if reset_page:
            self._reset_pagination()
        # ① Task list (updates _total_count, pagination, auto_select_first)
        self._refresh_task_list(filter_)
        # ② Stats bar (date range aligned to filter)
        self._stats_bar.set_partition_id(self._active_partition_id)
        # Determine lower bound: use last archive time for "全部" and "逾期"
        last_archive = self._repository.get_last_archive_time()
        archive_bound = last_archive.date() if last_archive else date(2000, 1, 1)

        if filter_.overdue_only:
            from datetime import timedelta as _td
            df, dt_to = archive_bound, date.today() - _td(days=1)
        elif filter_.date_to and not filter_.date_from:
            # "week" preset: upper bound only, stats up to end of week
            df, dt_to = archive_bound, filter_.date_to
        elif filter_.date_from and filter_.date_to:
            df, dt_to = filter_.date_from, filter_.date_to
        else:
            # "today" / "all": from last archive to now (or all time)
            df, dt_to = archive_bound, date(2100, 1, 1)
        self._stats_bar.refresh(date_from=df, date_to=dt_to, overdue_only=filter_.overdue_only)
        # ③ Carousel
        self._update_carousel(filter_)
        # ④ Status bar
        self._update_status_partition_label()

    def _update_status_partition_label(self) -> None:
        """Show context-aware status bar: partition + filter summary + encouragement."""
        if not self._active_partition_id:
            return
        # Show locked state if masked
        if self._splitter_stack.currentIndex() == 1:
            name = self._get_partition_name(self._active_partition_id)
            self._status_partition.setText(f"  🔒 {name} · 已锁定，点击解锁按钮重试")
            from ..utils.design_tokens import get_tokens as _gt
            self._status_partition.setStyleSheet(
                f"color: {_gt().danger}; font-size: 12px; font-weight: bold; padding: 2px 10px;"
            )
            return
        name = self._get_partition_name(self._active_partition_id)
        # Determine filter context
        f = self._carousel_filter or TaskFilter()
        today = date.today()
        if f.overdue_only:
            ctx = "逾期"
        elif f.date_from == today and f.date_to == today:
            ctx = "今日"
        elif f.date_from and f.date_to and (f.date_to - f.date_from).days == 6:
            ctx = "本周"
        else:
            ctx = "全部"

        # Use total_count from the last refresh (consistent with task list + stats bar)
        total = getattr(self, '_total_count', 0)

        if total == 0:
            motd = self._config.get("motd", default={})
            key_map = {"今日": "today", "本周": "week", "逾期": "overdue", "全部": "all"}
            msg = motd.get(key_map.get(ctx, "all"), "")
            self._status_partition.setText(f"  📂 {name} :: [{ctx}] {msg}")
            from ..utils.design_tokens import get_tokens as _gt3
            self._status_partition.setStyleSheet(
                f"color: {_gt3().text_secondary}; font-size: 12px; padding: 2px 10px;"
            )
        else:
            counts = self._stats_bar.get_counts()
            ov = counts.get(TaskStatus.OVERDUE, 0)
            t = counts.get(TaskStatus.TODO, 0)
            d = counts.get(TaskStatus.DOING, 0)
            dn = counts.get(TaskStatus.DONE, 0)
            total = ov + t + d + dn  # sum of stats bar = consistent with badges
            self._status_partition.setText(
                f"  📂 {name} :: [{ctx}] 逾期{ov} 待办{t} 进行中{d} 已完成{dn}"
                f" (共{total}条)  |  合理安排时间 ⏰"
            )
            from ..utils.design_tokens import get_tokens as _gt4
            self._status_partition.setStyleSheet(
                f"color: {_gt4().accent}; font-size: 12px; font-weight: bold;"
                " padding: 2px 10px;"
            )

    def _on_task_created(self, task: Task) -> None:
        """Refresh and select the newly created task."""
        self._on_data_changed()
        model = self._task_view.model()
        if model is None:
            return
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            t = idx.data(Qt.ItemDataRole.UserRole)
            if t and t.id == task.id:
                sm = self._task_view.selectionModel()
                if sm is not None:
                    sm.setCurrentIndex(idx, sm.SelectionFlag.SelectCurrent | sm.SelectionFlag.Rows)
                self._task_view.scrollTo(idx)
                self._edit_panel.load_task(task)
                break

    def _on_task_deleted(self, task_id: str) -> None:
        if self._edit_panel.current_task() and self._edit_panel.current_task().id == task_id:
            self._edit_panel.clear()
        self._on_data_changed()

    def _refresh_task_list(self, filter_: TaskFilter | None = None) -> None:
        # Skip data loading when partition is locked
        if hasattr(self, '_splitter_stack') and self._splitter_stack.currentIndex() == 1:
            return
        if filter_ is None:
            filter_ = self._filter_bar.build_filter()
        if self._active_partition_id:
            filter_.partition_id = self._active_partition_id
        # Count total first
        self._total_count = self._repository.count(filter_)
        # Apply pagination
        filter_.limit = self._page_size
        filter_.offset = self._page * self._page_size
        tasks = self._repository.search(filter_)
        self._task_model.set_offset(self._page * self._page_size)
        self._task_model.load_tasks(tasks)
        self._update_page_label()
        self._auto_select_first()

    def _update_page_label(self) -> None:
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        self._page_label.setText(f"{self._page + 1} / {total_pages}")
        self._page_prev_btn.setEnabled(self._page > 0)
        self._page_next_btn.setEnabled(self._page < total_pages - 1)

    def _on_page_prev(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._on_data_changed()

    def _on_page_next(self) -> None:
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        if self._page < total_pages - 1:
            self._page += 1
            self._on_data_changed()

    def _on_page_size_changed(self, text: str) -> None:
        self._page_size = int(text)
        self._page = 0
        self._config.set("general", "page_size", value=self._page_size)
        self._config.save()
        self._on_data_changed()

    def _reset_pagination(self) -> None:
        """Reset to first page on filter/partition change."""
        self._page = 0

    def _auto_select_first(self) -> None:
        """Auto-select the first (most important) task in the current list.
        If the list is empty, show an encouraging empty-state message.
        If a task is already being edited, keep it selected."""
        all_tasks = self._task_model.tasks
        # Keep current selection if it still exists in model, but refresh timeline
        cur = self._edit_panel.current_task()
        if cur and cur.id:
            for t in all_tasks:
                if t.id == cur.id:
                    self._edit_panel.load_task(t)
                    return
        if not all_tasks:
            self._edit_panel.show_empty()
            return

        # Sort: status importance → closest deadline
        status_rank = {
            TaskStatus.OVERDUE: 0, TaskStatus.TODO: 1,
            TaskStatus.DOING: 2, TaskStatus.DONE: 3,
        }
        sorted_tasks = sorted(
            all_tasks,
            key=lambda t: (
                status_rank.get(t.status, 99),
                t.deadline_date or date.max,
                t.scheduled_date or date.max,
            ),
        )
        best = sorted_tasks[0]
        model = self._task_view.model()
        if model is None:
            return
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            task = idx.data(Qt.ItemDataRole.UserRole)
            if task and task.id == best.id:
                sm = self._task_view.selectionModel()
                if sm is not None:
                    sm.setCurrentIndex(idx, sm.SelectionFlag.SelectCurrent | sm.SelectionFlag.Rows)
                self._task_view.scrollTo(idx)
                self._edit_panel.load_task(task)
                break

    def _load_partitions(self) -> None:
        """Populate toolbar partition menu from repository. No '全部' option."""
        all_partitions = self._repository.get_all_partitions()
        hidden = set(self._config.get("general", "hidden_partitions", default=[]))
        visible = [p for p in all_partitions if p["id"] not in hidden]
        self._partition_passwords = {p["id"]: p.get("password", "") for p in all_partitions}

        # Rebuild menu with checkable items (current partition marked)
        self._partition_menu.clear()
        for p in visible:
            action = self._partition_menu.addAction(p["name"])
            action.setData(p["id"])
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, pid=p["id"]: self._on_partition_menu_selected(pid)
            )

        # Determine active partition: last used → first visible → first overall
        last_id = self._config.get("general", "last_partition_id", default="")
        if last_id and any(p["id"] == last_id for p in visible):
            target_id = last_id
        elif visible:
            target_id = visible[0]["id"]
        else:
            target_id = all_partitions[0]["id"] if all_partitions else ""
        self._active_partition_id = target_id
        # If password-protected, lock immediately — user clicks "解锁" to prompt
        if self._partition_passwords.get(target_id, ""):
            self._lock_partition(target_id)
        else:
            name = self._get_partition_name(target_id)
            self._partition_btn.setToolTip(f"当前分区：{name}")
            self._edit_panel.set_active_partition(target_id)
            self._activate_partition(target_id)
            # Ensure partition is always visible in status bar
            self._status_partition.setText(f"  📂 {name}")
            from ..utils.design_tokens import get_tokens as _gt5
            self._status_partition.setStyleSheet(
                f"color: {_gt5().accent}; font-size: 12px; font-weight: bold; padding: 2px 10px;"
            )

    def _update_partition_menu_check(self) -> None:
        """Mark the currently active partition in the dropdown menu."""
        active = self._active_partition_id
        for action in self._partition_menu.actions():
            action.setChecked(action.data() == active)

    def _on_partition_menu_selected(self, new_id: str) -> None:
        """Handle partition switch from menu — check password, then refresh."""
        if new_id == self._active_partition_id:
            return
        if self._partition_passwords.get(new_id, ""):
            name = self._get_partition_name(new_id)
            while True:
                pwd, ok = QInputDialog.getText(
                    self, "加密分区",
                    f"进入「{name}」分区需要密码\n请输入密码：",
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    self._flash_status("已取消切换")
                    return
                if not pwd.strip():
                    QMessageBox.warning(self, "提示", "请输入密码。")
                    continue
                if pwd != self._partition_passwords[new_id]:
                    self._lock_partition(new_id)
                    self._flash_status("🔒 密码错误，内容已隐藏。点击解锁按钮重试")
                    return
                break
        self._activate_partition(new_id)
        self._reset_idle_lock_timer()

    def _activate_partition(self, new_id: str) -> None:
        """Activate a partition and refresh all views, defaulting to today filter."""
        self._active_partition_id = new_id
        self._splitter_stack.setCurrentIndex(0)
        self._partition_btn.setToolTip(f"当前分区：{self._get_partition_name(new_id)}")
        self._config.set("general", "last_partition_id", value=new_id)
        self._config.save()
        self._update_partition_menu_check()
        self._edit_panel.set_active_partition(new_id)
        self._reset_pagination()
        # Reset to "all" filter on partition switch so users see everything
        self._carousel_filter = None
        self._filter_bar.reset()
        self._filter_bar.filter_changed.emit(self._filter_bar.build_filter())

    def _on_unlock_partition(self) -> None:
        """Retry password for the currently locked partition."""
        new_id = self._active_partition_id
        if not new_id or not self._partition_passwords.get(new_id, ""):
            return
        name = self._get_partition_name(new_id)
        while True:
            pwd, ok = QInputDialog.getText(
                self, "解锁分区",
                f"「{name}」分区已锁定\n请输入密码解锁：",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            if not pwd.strip():
                QMessageBox.warning(self, "提示", "请输入密码。")
                continue
            if pwd == self._partition_passwords[new_id]:
                self._activate_partition(new_id)
                self._flash_status("🔓 已解锁，欢迎回来")
                self._reset_idle_lock_timer()
                return
            self._flash_status("🔒 密码错误，请重试")
            return

    def _get_partition_name(self, pid: str) -> str:
        for p in self._repository.get_all_partitions():
            if p["id"] == pid:
                return p["name"]
        return "全部"

    def _lock_partition(self, target_id: str) -> None:
        """Lock a partition: show mask, empty data, update UI."""
        name = self._get_partition_name(target_id)
        self._partition_btn.setToolTip(f"当前分区：{name}（已锁定）")
        self._splitter_stack.setCurrentIndex(1)
        self._config.set("general", "last_partition_id", value=target_id)
        self._config.save()
        self._update_partition_menu_check()
        # Show empty: load nothing into task list, stats show 0
        self._task_model.load_tasks([])
        self._edit_panel.clear()
        self._update_status_partition_label()
        self._carousel.set_items([])
        # Force stats bar to show all zeros
        for status in (TaskStatus.OVERDUE, TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            badge = self._stats_bar._badges.get(status)
            if badge:
                badge.setText(f"{badge.text().split(':')[0]}: 0")

    def _find_first_unlocked_partition(self) -> str | None:
        """Find the first partition without a password."""
        for pid, pwd in self._partition_passwords.items():
            if not pwd:
                return pid
        return None

    def _flash_status(self, msg: str) -> None:
        """Show a temporary message in the status bar (3 seconds)."""
        self._status_partition.setText(f"  {msg}")
        from ..utils.design_tokens import get_tokens as _gt2
        self._status_partition.setStyleSheet(
            f"color: {_gt2().danger}; font-size: 12px; font-weight: bold; padding: 2px 10px;"
        )
        QTimer.singleShot(3000, self._update_status_partition_label)

    def _on_partitions_changed(self) -> None:
        """Refresh partition data across all components."""
        self._load_partitions()
        self._on_data_changed()

    def _update_carousel(self, filter_: TaskFilter | None = None) -> None:
        if filter_ is not None:
            f = filter_
        else:
            f = TaskFilter()
        if self._active_partition_id:
            f.partition_id = self._active_partition_id
        tasks = self._repository.search(f)

        active = [t for t in tasks if t.status != TaskStatus.DONE]
        done = [t for t in tasks if t.status == TaskStatus.DONE]

        items: list[dict] = []
        for t in active:
            items.append({
                "task_id": t.id,
                "text": t.title,
                "color": t.status.display_color,
            })
        for t in done:
            items.append({
                "task_id": t.id,
                "text": f"✓ {t.title}",
                "color": "#27ae60",
            })

        self._carousel.set_items(items[:10])

    # ------------------------------------------------------------------
    # Slots: filters
    # ------------------------------------------------------------------

    def _on_filter_changed(self, filter_: TaskFilter) -> None:
        if not self._guard_draft():
            return
        self._stack.setCurrentIndex(0)
        # Ensure mask is hidden (belt-and-suspenders for stale lock state)
        if hasattr(self, '_splitter_stack'):
            self._splitter_stack.setCurrentIndex(0)
        self._carousel_filter = filter_
        self._edit_panel.clear()
        self._refresh_all_views(filter_, reset_page=True)
        # Safety: ensure first result is selected
        self._auto_select_first()

    def _on_stats_filter(self, filter_: TaskFilter) -> None:
        if not self._guard_draft():
            return
        self._stack.setCurrentIndex(0)
        self._carousel_filter = filter_
        self._filter_bar.blockSignals(True)
        self._filter_bar.reset()
        self._filter_bar.blockSignals(False)
        self._edit_panel.clear()
        self._refresh_all_views(filter_, reset_page=True)
        self._auto_select_first()

    # ------------------------------------------------------------------
    # Slots: task interaction
    # ------------------------------------------------------------------

    def _on_task_selected(self, task: Task) -> None:
        if not self._guard_draft():
            return
        self._edit_panel.load_task(task)

    def _on_detail_requested(self, task: Task) -> None:
        if not self._guard_draft():
            return
        self._stack.setCurrentIndex(0)
        self._edit_panel.show_details(task)

    def _on_carousel_clicked(self, task_id: str) -> None:
        if not self._guard_draft():
            return
        task = self._repository.get_by_id(task_id)
        if task:
            self._stack.setCurrentIndex(0)
            self._edit_panel.show_details(task)

    def _on_go_home(self) -> None:
        """Logo clicked — return to main task view."""
        if not self._guard_draft():
            return
        self._save_splitter_state()
        self._stack.setCurrentIndex(0)
        self._filter_bar.reset()
        self._filter_bar.filter_changed.emit(self._filter_bar.build_filter())
        self._restore_splitter_state()

    def _save_splitter_state(self) -> list[int]:
        """Save current splitter sizes."""
        self._saved_sizes = list(self._splitter.sizes())
        return self._saved_sizes

    def _restore_splitter_state(self) -> None:
        """Restore saved splitter sizes if they look valid."""
        sizes = getattr(self, "_saved_sizes", None)
        if sizes and sum(sizes) > 100:
            self._splitter.setSizes(sizes)

    def _on_preset_filter(self, preset: str) -> None:
        if not self._guard_draft():
            return
        self._stack.setCurrentIndex(0)
        today = date.today()
        self._filter_bar.reset()

        if preset == "all":
            self._filter_bar.filter_changed.emit(self._filter_bar.build_filter())
        elif preset == "today":
            # "Today" = all active tasks regardless of deadline.
            # Deadline is task metadata, not a visibility filter.
            self._filter_bar.filter_changed.emit(self._filter_bar.build_filter())
        elif preset == "week":
            weekday = today.isoweekday()
            monday = today - dt.timedelta(days=weekday - 1)
            sunday = monday + dt.timedelta(days=6)
            f = self._filter_bar.build_filter()
            f.date_to = sunday  # includes overdue + this week
            self._filter_bar.filter_changed.emit(f)
        elif preset == "overdue":
            f = self._filter_bar.build_filter()
            f.overdue_only = True
            self._filter_bar.filter_changed.emit(f)

    def _on_new_task(self) -> None:
        """Ctrl+N — same as clicking the '新建' toolbar button."""
        self._on_new_draft()

    def _on_new_draft(self) -> None:
        """Create a draft TODO task — reset to today view first."""
        if not self._guard_draft():
            return
        self._stack.setCurrentIndex(0)
        self.show()
        self.raise_()
        self.activateWindow()
        f = self._filter_bar.build_filter()
        if self._active_partition_id:
            f.partition_id = self._active_partition_id
        self._filter_bar.filter_changed.emit(f)
        self._edit_panel.create_draft()

    def _guard_draft(self) -> bool:
        """If there is an unsaved draft, prompt before navigating away.
        Returns False if the user cancels (navigation should abort)."""
        if not self._edit_panel.has_unsaved_draft():
            return True
        result = QMessageBox.question(
            self, "未保存的草稿",
            "当前有未保存的新建任务，是否保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Save:
            self._edit_panel._on_save()
            return True
        if result == QMessageBox.StandardButton.Discard:
            self._edit_panel.discard_draft()
            return True
        return False

    # ------------------------------------------------------------------
    # Slots: import / export
    # ------------------------------------------------------------------

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Markdown", "", "Markdown 文件 (*.md);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "导入失败", f"无法读取文件：{e}")
            return

        parser = MarkdownTaskParser()
        results = parser.parse_batch(text)
        imported = 0
        errors = 0
        for parsed, raw_line, err in results:
            if parsed is not None:
                now = datetime.now()
                task = Task(
                    id="",
                    raw_md=raw_line,
                    title=parsed.title,
                    status=parsed.status,
                    tags=parsed.tags,
                    scheduled_date=parsed.scheduled_date,
                    deadline_date=parsed.deadline_date,
                    created_at=now,
                    updated_at=now,
                    activity_log=[{
                        "ts": now.isoformat(),
                        "content": "创建任务",
                        "status": parsed.status.value,
                        "progress": 0,
                    }],
                )
                self._repository.insert(task)
                imported += 1
                self._signal_bus.task_created.emit(task)
            else:
                errors += 1

        msg = f"成功导入 {imported} 个任务。"
        if errors:
            msg += f"\n{errors} 行解析失败。"
        QMessageBox.information(self, "导入完成", msg)
        self._signal_bus.scan_completed.emit(imported)

    def _on_export(self) -> None:
        default_name = f"tasks_{date.today().isoformat()}.md"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown", default_name, "Markdown 文件 (*.md)"
        )
        if not path:
            return

        tasks = self._repository.get_all()
        formatter = MarkdownTaskFormatter()
        lines = [formatter.format(t) for t in tasks if not t.archived]

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError as e:
            QMessageBox.warning(self, "导出失败", f"无法写入文件：{e}")
            return

        QMessageBox.information(self, "导出完成", f"成功导出 {len(lines)} 个任务。")

    # ------------------------------------------------------------------
    # Slots: navigation
    # ------------------------------------------------------------------

    def _on_settings(self) -> None:
        dialog = SettingsDialog(self._config, self._repository, parent=self)
        dialog.exec()
        self._signal_bus.config_changed.emit()

    def _on_config_changed(self) -> None:
        """Sync filter bar sort when default sort config changes."""
        self._filter_bar.set_sort(self._config.default_sort)

    # ------------------------------------------------------------------
    # Midnight timer — refreshes stats when the day boundary crosses
    # ------------------------------------------------------------------

    def _setup_midnight_timer(self) -> None:
        self._midnight_timer = QTimer(self)
        self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight_crossed)
        self._schedule_midnight_timer()

    def _schedule_midnight_timer(self) -> None:
        now = QDateTime.currentDateTime()
        tomorrow = now.date().addDays(1)
        midnight = QDateTime(tomorrow, QTime(0, 0, 0))
        self._midnight_timer.start(now.msecsTo(midnight))

    def _on_midnight_crossed(self) -> None:
        """Day boundary crossed — refresh overdue status and stats."""
        changed = self._repository.refresh_overdue_status()
        for task, old_status in changed:
            self._signal_bus.task_status_changed.emit(task, old_status)
        self._on_data_changed()
        self._schedule_midnight_timer()

    def _on_quit(self) -> None:
        self._signal_bus.application_quit.emit()

    def _on_refresh(self) -> None:
        self._save_splitter_state()
        self._on_data_changed()
        self._restore_splitter_state()

    def _on_toggle_heatmap(self) -> None:
        if not self._guard_draft():
            return
        current = self._stack.currentIndex()
        target = 1 if current == 0 else 0
        self._stack.setCurrentIndex(target)
        if target == 1:
            self._heatmap_widget.refresh()

    def _on_about(self) -> None:
        dialog = AboutDialog(parent=self)
        dialog.exec()

    def _on_date_selected(self, selected_date: date) -> None:
        if not self._guard_draft():
            return
        self._stack.setCurrentIndex(0)
        self._filter_bar.blockSignals(True)
        self._filter_bar.reset()
        self._filter_bar.blockSignals(False)
        f = self._filter_bar.build_filter()
        f.date_from, f.date_to = selected_date, selected_date
        self._filter_bar.filter_changed.emit(f)
