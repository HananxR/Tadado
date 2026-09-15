"""Main window — Todoseq-style layout with custom title bar and adaptive sizing."""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QDateTime, QEvent, QPoint, QSize, Qt, QTime, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from ..config import AppConfig
from ..models.repository import TaskRepository
from ..services.update_checker import UpdateChecker
from ..utils.icon_loader import load_icon
from ..utils.signal_bus import get_signal_bus
from .controllers.analysis_controller import AnalysisController
from .controllers.batch_controller import BatchController
from .controllers.partition_controller import PartitionController
from .selection_context import SelectionContext
from .toast import Toast
from .window_shell import WindowShell

_log = logging.getLogger("runlog")


class MainWindow(QMainWindow):
    """Desktop task manager with Markdown-first workflow."""

    def __init__(
        self,
        config: AppConfig,
        repository: TaskRepository,
        task_service=None,  # TaskService (optional, for gradual migration)
    ) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        # ── DWM pre-config: must run BEFORE show(), right after HWND creation ──
        # Force native HWND creation so DWM attributes can be set immediately,
        # before DWM ever composites a single frame for this window.
        self.winId()
        from ..utils.win32_theme import (
            enable_window_snap,
            set_window_cloaked,
            set_window_nc_rendering_disabled,
        )

        set_window_nc_rendering_disabled(self)  # never draw native NC buttons
        set_window_cloaked(self, True)  # hide from DWM until fully ready
        enable_window_snap(self)  # restore WS_THICKFRAME for Aero Snap
        # ──────────────────────────────────────────────────────────────────────

        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._config = config
        self._last_applied_theme = config.theme
        self._last_default_pid: str = config.get("general", "default_partition", default="")
        self._repository = repository
        self._task_service = task_service
        self._signal_bus = get_signal_bus()
        # 跨视图共享选中上下文（阶段 1 引入，阶段 3 时间轴首次真正接入）
        self._selection = SelectionContext(self)
        self._current_view: str = "edit"
        self._current_page: str = "tasks"
        self._update_checker = UpdateChecker(self)
        # 窗口生命周期收敛层：唤醒 / 置顶 / 全局热键（阶段 5）
        self._window_shell = WindowShell(self, config, self)

        self.setWindowTitle("Tadado")

        self._setup_custom_title_bar()
        self._setup_central_widget()
        # 反馈浮层（原型 #toast）——取代 1.0 的底部状态栏
        self._toast = Toast(self)
        # PartitionController — owns partition lifecycle, replaces _setup_idle_lock + _load_partitions
        self._partition_ctrl = PartitionController(
            self._task_service,
            self._config,
            self._splitter_stack,
            self._nav_shell.partition_selector,
            self,
        )
        self._partition_ctrl.partition_activated.connect(self._on_partition_activated)
        # BatchController — lazily builds page2
        self._batch_ctrl = BatchController(
            self._task_service,
            self._config,
            self._partition_ctrl,
            self,
        )
        self._batch_ctrl.status_message.connect(self._flash_status)
        # AnalysisController — 活动分析页槽与导出（页面部件懒构建后 attach）
        self._analysis_ctrl = AnalysisController(self._task_service, self)
        self._analysis_ctrl.set_partition(self._partition_ctrl.active_id)
        self._connect_signals()
        self._setup_midnight_timer()
        self._partition_ctrl.load_all()
        self._window_shell.apply_configured_pin()

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
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_batch_splitter_sizes()
        toast = getattr(self, "_toast", None)
        if toast is not None:
            toast.reposition()
        # 抽屉是自由浮动的子部件（不在布局里），窗口缩放时要手动重新贴右
        for attr in ("_task_drawer", "_settings_drawer"):
            drawer = getattr(self, attr, None)
            if drawer is not None and drawer.is_open:
                drawer.reposition()

    def _apply_batch_splitter_sizes(self) -> None:
        """Set batch page splitter to 70:30 (existing content : tag panel)."""
        splitter = self._batch_ctrl.splitter
        if splitter is None:
            return
        total = splitter.width()
        if total > 100:
            splitter.setSizes([int(total * 0.80), int(total * 0.20)])

    def refresh_theme(self) -> None:
        # 标题栏 / 侧栏 / 浮层样式由 MainWindow 自己持有，不参与注册表
        if hasattr(self, "_title_icon_btn"):
            self._refresh_title_bar_theme()
        if hasattr(self, "_nav_shell"):
            self._nav_shell.refresh_theme()
        if hasattr(self, "_toast"):
            self._toast.refresh_theme()
        # 其余部件在构造时自助登记，这里统一广播（弱引用，销毁自动摘除）
        from ..utils.theme_registry import refresh_theme_all

        refresh_theme_all()

    def _refresh_title_bar_theme(self) -> None:
        """Re-apply inline QSS on the title-bar logo button after theme switch."""
        from ..utils.design_tokens import get_tokens as _gt

        t = _gt()
        self._title_icon_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; padding: 0px; }}"
            f"QPushButton:hover {{ background: {t.accent}20; }}"
        )

    def active_partition_name(self) -> str:
        """当前激活分区的名称（供托盘 AI 助手注入 TADADO_PARTITION）."""
        pid = self._partition_ctrl.active_id or ""
        return self._task_service.get_partition_name_map().get(pid, "")

    # ------------------------------------------------------------------
    # Public API — 供托盘 / app 调用（不再触碰私有槽）
    # ------------------------------------------------------------------

    @property
    def window_shell(self) -> WindowShell:
        return self._window_shell

    def wake(self, switch_to: str | None = None) -> None:
        """显示并聚焦窗口（可选同时切页）。"""
        self._window_shell.wake(switch_to=switch_to)

    def toggle_visibility(self) -> None:
        """托盘「显示/隐藏窗口」。"""
        self._window_shell.toggle_visibility()

    def new_single_task(self) -> None:
        """托盘「新建单任务」。"""
        self._on_menu_new_draft()

    def new_multi_task(self) -> None:
        """托盘「新建多任务」。"""
        self._on_menu_new_multi()

    def quit_app(self) -> None:
        """托盘「退出」。"""
        self._on_quit()

    # ------------------------------------------------------------------
    # Custom title bar — VS Code style: icon + menu + window buttons
    # ------------------------------------------------------------------

    def _setup_custom_title_bar(self) -> None:
        bar_h = 36

        title_bar = QWidget()
        title_bar.setObjectName("customTitleBar")
        title_bar.setFixedHeight(bar_h)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(0)

        # Logo button
        self._title_icon_btn = QPushButton()
        self._title_icon_btn.setIcon(load_icon("app"))
        self._title_icon_btn.setIconSize(QSize(20, 20))
        self._title_icon_btn.setFixedSize(bar_h, bar_h)
        self._title_icon_btn.setFlat(True)
        self._title_icon_btn.setToolTip("返回主界面")
        self._title_icon_btn.clicked.connect(self._on_go_home)
        self._refresh_title_bar_theme()
        tb.addWidget(self._title_icon_btn)

        # 全局热键提示（Phase 5 落地实际热键注册）
        hint_label = QLabel("⌨ Ctrl+Shift+Space 随时唤起")
        hint_label.setObjectName("titleHint")
        from ..utils.design_tokens import get_tokens as _get_tokens

        _tokens = _get_tokens()
        _hint_color = _tokens.text_secondary if _tokens else "#9a9488"
        hint_label.setStyleSheet(
            f"color: {_hint_color}; font-size: 11px; padding: 0 8px;"
        )
        tb.addWidget(hint_label)

        tb.addStretch()

        # 常驻置顶按钮（TODO(phase5): WindowShell 接管）
        from ..utils.design_tokens import get_tokens as _gt

        _accent = _gt().accent
        self._pin_btn = QPushButton()
        self._pin_btn.setIcon(load_icon("pin"))
        self._pin_btn.setIconSize(QSize(16, 16))
        self._pin_btn.setFixedSize(bar_h - 6, bar_h - 6)
        self._pin_btn.setFlat(True)
        self._pin_btn.setCheckable(True)
        self._pin_btn.setToolTip("常驻置顶")
        self._pin_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0px; }"
            f"QPushButton:checked {{ background: rgba({int(_accent[1:3], 16)},"
            f"{int(_accent[3:5], 16)},{int(_accent[5:7], 16)},0.22); border-radius: 6px; }}"
        )
        self._pin_btn.clicked.connect(self._toggle_pin)
        tb.addWidget(self._pin_btn)

        # Right-side window buttons (icon only) — colors via base.qss
        right_btn_style = "QPushButton { border: none; background: transparent; padding: 0px; }"
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
            elif msg.message == 0x0083:  # WM_NCCALCSIZE
                # Extend the client area to cover the entire window rect.
                # wParam==0 → simple RECT; wParam==1 → NCCALCSIZE_PARAMS.
                # In both cases we return True,0 to claim we handled it and
                # request the full window area — the invisible border added
                # by WS_THICKFRAME must not shrink our client area.
                return True, 0
            elif msg.message == 0x0024:  # WM_GETMINMAXINFO
                # Let DefWindowProc handle it; the default maximised monitor
                # rect works correctly with WS_THICKFRAME on Win10/11.
                return False, 0
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
        border = 8  # match Win10/11 standard invisible resize border
        g = self.geometry()
        title_h = 36
        if g.y() <= y < g.y() + title_h:
            # Use childAt() to distinguish buttons from empty draggable space.
            # Any child widget under the cursor → HTCLIENT (button works).
            # Empty area → HTCAPTION (entire title bar can drag to Snap).
            bar = self.menuWidget()
            if bar is not None:
                local = bar.mapFromGlobal(QPoint(x, y))
                if bar.childAt(local) is not None:
                    return False, 0  # HTCLIENT — button receives click
            return True, 2  # HTCAPTION — draggable
        left = x < g.x() + border
        right = x > g.x() + g.width() - border
        top = y < g.y() + border
        bottom = y > g.y() + g.height() - border
        if top and left:
            return True, 13
        if top and right:
            return True, 14
        if bottom and left:
            return True, 16
        if bottom and right:
            return True, 17
        if left:
            return True, 10
        if right:
            return True, 11
        if bottom:
            return True, 15
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
        from .nav_shell import NavShell
        from .views import VIEW_REGISTRY, get_spec

        self._page_index: dict[str, int] = {}
        self._page_built: dict[str, bool] = {}
        self._stack = QStackedWidget()
        for i, page_id in enumerate(VIEW_REGISTRY.keys()):
            self._page_index[page_id] = i
            self._stack.addWidget(QWidget())  # placeholder, replaced on first access
            self._page_built[page_id] = False

        # 侧边栏：分组入口 + 设置齿轮
        self._nav_shell = NavShell(self)
        self._nav_shell.page_requested.connect(self._switch_view)
        self._nav_shell.settings_requested.connect(self._on_settings)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._nav_shell)
        central_layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        # 默认显示任务页（旧行为：page0 = edit view，随窗口构建即建）
        spec = get_spec("tasks")
        task_page = spec.factory(None, {"main_window": self})
        idx = self._page_index["tasks"]
        old = self._stack.widget(idx)
        self._stack.removeWidget(old)
        if old:
            old.deleteLater()
        self._stack.insertWidget(idx, task_page)
        self._page_built["tasks"] = True
        # 必须显式切到任务页：insertWidget 不会改变 currentIndex，
        # 否则启动后主区域停留在 overview 的空占位（且 _switch_view 因
        # `_current_view` 初值 "edit" 会被 early-return 拦下，无法补救）。
        self._stack.setCurrentIndex(idx)
        self._nav_shell.set_active("tasks")

    def _toggle_pin(self) -> None:
        """常驻置顶（阶段 5：交由 WindowShell 统一管理）。"""
        on = self._pin_btn.isChecked()
        self._window_shell.set_pinned(on)
        self._flash_status("已开启常驻置顶" if on else "已取消常驻置顶")

    def _on_new_multi_task(self) -> None:
        """批量新建（托盘 / 菜单入口）。"""
        self._ensure_window_ready()
        self._open_multi_task_dialog()

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        bus = self._signal_bus

        # Partitions → PartitionController
        bus.partitions_changed.connect(self._partition_ctrl.load_all)

        # Config → MainWindow (cross-cutting)
        bus.config_changed.connect(self._on_config_changed)

        # Heatmap refresh (widget concern)
        bus.task_created.connect(self._on_heatmap_data_changed)
        bus.task_updated.connect(self._on_heatmap_data_changed)
        bus.task_deleted.connect(self._on_heatmap_data_changed)
        bus.task_status_changed.connect(self._on_heatmap_data_changed)
        bus.batch_operation_completed.connect(self._on_heatmap_data_changed)

        # 状态 chips 计数（原型「全部 28」形式）
        for signal in (
            bus.task_created,
            bus.task_updated,
            bus.task_deleted,
            bus.task_status_changed,
            bus.batch_operation_completed,
            bus.archive_completed,
            bus.scan_completed,
        ):
            signal.connect(self._on_bus_refresh_chips)

        # Timeline：选中 / 双击 / 搜索 / 状态 / 排序 / 粒度
        self._timeline_ctl.task_selected.connect(self._on_timeline_selected)
        self._timeline_ctl.task_activated.connect(self._on_timeline_activated)
        self._timeline_search.textChanged.connect(self._apply_timeline_filters)
        self._timeline_sort_combo.currentIndexChanged.connect(
            self._on_timeline_sort_changed
        )
        self._timeline_range_seg.changed.connect(self._on_timeline_range_changed)
        self._status_chip_group.buttonClicked.connect(self._apply_timeline_filters)

        # 页头「＋ 新建任务」
        self._new_task_btn.clicked.connect(self._on_new_task)

    def _on_heatmap_data_changed(self, *args) -> None:
        if hasattr(self, "_heatmap_widget"):
            self._heatmap_widget.force_refresh()

    def _on_go_home(self) -> None:
        if self._current_view != "edit":
            self._switch_view("edit")
        # 回到首页 = 工具行过滤全部复位 + 时间轴回到「默认粒度」
        default_range = self._config.timeline_range
        self._timeline_search.clear()
        self._timeline_status_chips["all"].setChecked(True)
        self._timeline_range_seg.set_current_value(default_range)
        self._timeline_ctl.set_range(default_range)
        self._apply_timeline_filters()

    # ------------------------------------------------------------------
    # Timeline (阶段 3)
    # ------------------------------------------------------------------

    def _on_timeline_selected(self, task_id: str) -> None:
        """时间轴单击 → 仅选中（高亮与 SelectionContext 由 TimelineController 负责）。"""

    def _on_timeline_activated(self, task_id: str) -> None:
        """双击时间轴 → 打开维护抽屉（阶段 4）。"""
        self._on_timeline_selected(task_id)
        self._ensure_drawer().open_task(task_id)

    # ------------------------------------------------------------------
    # TaskDrawer (阶段 4)
    # ------------------------------------------------------------------

    def _ensure_drawer(self):
        """惰性创建维护抽屉（首次双击时才构建）。"""
        drawer = getattr(self, "_task_drawer", None)
        if drawer is None:
            from .drawer import TaskDrawer

            parent = self.centralWidget() or self
            drawer = TaskDrawer(self._task_service, parent, animate=True)
            drawer.saved.connect(self._on_drawer_saved)
            self._task_drawer = drawer
        return drawer

    def _on_drawer_saved(self, task_id: str) -> None:
        """抽屉保存后的即时反馈；按设置决定是否顺带收起抽屉。"""
        self._flash_status("已保存")
        if not self._config.auto_collapse_drawer:
            return
        drawer = getattr(self, "_task_drawer", None)
        if drawer is not None and drawer.is_open:
            drawer.close_drawer()

    def _on_timeline_range_changed(self, key) -> None:
        if key:
            self._timeline_ctl.set_range(key)
            # 记住用户的选择，作为下次启动 / 回到首页的默认粒度
            if key != self._config.timeline_range:
                self._config.set("general", "timeline_range", value=key)
                self._config.save()

    def _on_timeline_sort_changed(self, index: int) -> None:
        key = self._timeline_sort_combo.itemData(index)
        if key:
            self._timeline_ctl.set_sort(key)

    def _apply_timeline_filters(self, *_args) -> None:
        """工具行 → 时间轴过滤的唯一入口。"""
        status = self._selected_status_filter()
        self._timeline_ctl.set_filters(
            statuses={status} if status is not None else None,
            search_text=self._timeline_search.text(),
            urgencies=None,
        )

    def _selected_status_filter(self):
        """当前状态 chip 对应的 :class:`TaskStatus`；「全部」返回 ``None``。"""
        from .views.tasks_view import STATUS_FILTERS

        for key, _label, status in STATUS_FILTERS:
            chip = self._timeline_status_chips.get(key)
            if chip is not None and chip.isChecked():
                return status
        return None

    def _on_bus_refresh_chips(self, *_args) -> None:
        """总线事件 → 刷新状态 chips 计数。

        用绑定方法而非 lambda：MainWindow 销毁时 Qt 会自动断连；lambda 不会，
        残留回调会在数据库关闭后仍被触发，并因持有 ``self`` 造成泄漏。
        """
        self._refresh_status_chip_counts()

    def _refresh_status_chip_counts(self) -> None:
        """把状态计数写回 chips 文案（原型「全部 28」形式）。

        口径与时间轴一致：**包含已归档任务**——分区 ``archive_days=0`` 时任务
        完成即归档，若这里排除归档，会出现「已完成 0」却有时间轴绿色色条的矛盾。
        中止（suspended）任务不计入，与 ``get_status_counts`` 的口径保持一致。
        """
        from ..models.task_filter import TaskFilter
        from ..models.task_status import TaskStatus
        from .views.tasks_view import STATUS_FILTERS

        if not hasattr(self, "_timeline_status_chips"):
            return

        filter_ = TaskFilter(partition_id=self._partition_ctrl.active_id or None)
        filter_.show_archived = True
        counts: dict = {}
        for task in self._task_service.search(filter_):
            if task.suspended:
                continue
            counts[task.status] = counts.get(task.status, 0) + 1

        mapping = {
            "all": sum(counts.values()),
            "overdue": counts.get(TaskStatus.OVERDUE, 0),
            "todo": counts.get(TaskStatus.TODO, 0),
            "doing": counts.get(TaskStatus.DOING, 0),
            "done": counts.get(TaskStatus.DONE, 0),
        }
        for key, label, _status in STATUS_FILTERS:
            chip = self._timeline_status_chips.get(key)
            if chip is not None:
                chip.setText(f"{label} {mapping.get(key, 0)}")

    def _select_first_timeline_task(self) -> None:
        """把时间轴首行载入编辑器。"""
        model = self._timeline_view.table_model
        if model.rowCount() == 0:
            return
        row = model.row_at(0)
        if row is not None:
            self._on_timeline_selected(row.task_id)

    # ------------------------------------------------------------------
    # Task graph (阶段 6)
    # ------------------------------------------------------------------

    def _on_graph_task_activated(self, task_id: str) -> None:
        """双击图谱任务节点 → 切到任务页并打开维护抽屉。"""
        self._switch_view("tasks")
        task = self._task_service.get_task(task_id)
        if task is not None:
            self._selection.select_task(task_id)
            self._ensure_drawer().open_task(task_id)

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def _flash_status(self, msg: str) -> None:
        """Transient feedback (原型 ``toast()``）——底部居中浮层，自动淡出。"""
        self._toast.show_message(msg)

    # ------------------------------------------------------------------
    # Partition management
    # ------------------------------------------------------------------
    # Partition coordination — widget updates when partition changes
    # ------------------------------------------------------------------

    def _on_partition_activated(self, pid: str) -> None:
        """Update all partition-aware widgets after a partition is activated."""
        self._heatmap_widget.set_partition_id(pid or None)
        if hasattr(self, "_timeline_ctl"):
            self._timeline_ctl.set_partition(pid or None)
            self._timeline_ctl.refresh()
        if hasattr(self, "_graph_ctl"):
            self._graph_ctl.set_partition(pid or None)
            self._graph_ctl.refresh()
        if hasattr(self, "_overview_page"):
            self._overview_page.set_partition(pid or None)
            self._overview_page.refresh()
        self._batch_ctrl.refresh_page()
        self._batch_ctrl.set_active_partition(pid or None)
        self._heatmap_widget.force_refresh()
        self._analysis_ctrl.set_partition(pid)
        if self._current_view == "dashboard":
            self._analysis_ctrl.refresh()
        if self._timeline_view.table_model.rowCount() > 0:
            self._select_first_timeline_task()

    # ------------------------------------------------------------------
    # View switching
    # ------------------------------------------------------------------

    def _switch_view(self, view: str) -> None:
        from .views import get_spec, resolve

        page_id = resolve(view)
        # 兼容旧代码读取 _current_view == "edit"/"batch"（死代码清理后移除映射）
        old_name = {"tasks": "edit", "analysis": "dashboard", "manage": "batch"}.get(
            page_id, page_id
        )
        if old_name == self._current_view:
            return
        _log.info("View switched: %s", page_id)
        self._current_view = old_name
        self._current_page = page_id

        # Cancel any pending deferred loads
        if hasattr(self, "_deferred_timer") and self._deferred_timer.isActive():
            self._deferred_timer.stop()

        # 懒构建：首次访问时经注册表工厂生成真实页面
        if not self._page_built.get(page_id):
            spec = get_spec(page_id)
            page = spec.factory(None, {"main_window": self})
            idx = self._page_index[page_id]
            old = self._stack.widget(idx)
            self._stack.removeWidget(old)
            if old:
                old.deleteLater()
            self._stack.insertWidget(idx, page)
            self._page_built[page_id] = True

        self._stack.setCurrentIndex(self._page_index[page_id])
        self._nav_shell.set_active(page_id)

        # 阶段 7：任务页不在前台时时间轴只标记 dirty，切回时回放
        if hasattr(self, "_timeline_ctl"):
            self._timeline_ctl.set_visible(page_id == "tasks")

        if page_id == "tasks":
            self._heatmap_widget.nav_bar.setVisible(False)
        elif page_id == "analysis":
            self._heatmap_widget.nav_bar.setVisible(True)
            self._deferred_timer = QTimer(self)
            self._deferred_timer.setSingleShot(True)
            self._deferred_timer.timeout.connect(
                lambda: self._analysis_ctrl.refresh()
            )
            self._deferred_timer.start(0)
        elif page_id == "manage":
            self._heatmap_widget.nav_bar.setVisible(False)
            self._apply_batch_splitter_sizes()
            self._batch_ctrl.refresh_page()
            self._batch_ctrl.set_active_partition(self._partition_ctrl.active_id or None)




    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    def _on_new_task(self) -> None:
        """新建任务（公开入口）。"""
        self._ensure_window_ready()
        self._open_new_task_dialog()

    def _on_menu_new_draft(self) -> None:
        """菜单栏：唤起窗口并打开单任务编辑对话框。"""
        self._ensure_window_ready()
        self._open_new_task_dialog()

    def _on_menu_new_multi(self) -> None:
        """菜单栏：唤起窗口并打开批量新建对话框。"""
        self._ensure_window_ready()
        self._open_multi_task_dialog()

    def _ensure_window_ready(self) -> None:
        """Show, raise and switch to the task view.

        Updates ``_current_view`` so subsequent view switches work correctly.
        """
        self._current_view = "edit"
        self._heatmap_widget.nav_bar.setVisible(False)
        if self._splitter_stack.currentIndex() == 1:
            if self._partition_ctrl.passwords.get(self._partition_ctrl.active_id, ""):
                self._partition_ctrl.unlock()
            else:
                self._splitter_stack.setCurrentIndex(0)
        self._stack.setCurrentIndex(self._page_index["tasks"])
        self._window_shell.wake()

    def _open_new_task_dialog(self) -> None:
        """单任务 Markdown 编辑对话框（新建）。"""
        from .dialogs.task_dialog import TaskDialog

        dialog = TaskDialog(
            self._task_service,
            None,
            parent=self,
        )
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            self._flash_status("已创建任务")

    def _open_multi_task_dialog(self) -> None:
        """批量新建：多行 Markdown 一次性创建。"""
        from .dialogs.multi_task_dialog import MultiTaskDialog

        dialog = MultiTaskDialog(
            self._task_service,
            partition_id=self._partition_ctrl.active_id or None,
            parent=self,
        )
        dialog.tasks_created.connect(
            lambda count: self._flash_status(f"已创建 {count} 个任务")
        )
        dialog.exec()

    def _on_settings(self) -> None:
        """打开设置抽屉（原型 ``#setDrawer``，不是模态弹窗）。

        抽屉内每项改动都会立即 ``config.save()`` 并广播 ``config_changed``，
        所以这里不需要「确认/取消」与变更比对。
        """
        self._ensure_settings_drawer().open_drawer()

    def _ensure_settings_drawer(self):
        """惰性创建设置抽屉（首次点齿轮时才构建）。"""
        drawer = getattr(self, "_settings_drawer", None)
        if drawer is None:
            from .drawer.settings_drawer import SettingsDrawer

            parent = self.centralWidget() or self
            drawer = SettingsDrawer(
                self._config,
                self._task_service,
                update_checker=self._update_checker,
                parent=parent,
            )
            self._settings_drawer = drawer
        return drawer

    def _on_quit(self) -> None:
        self._signal_bus.application_quit.emit()

    def _on_refresh(self) -> None:
        self._timeline_ctl.refresh()

    def _on_config_changed(self) -> None:
        data_changed = False
        theme_changed = self._config.theme != self._last_applied_theme

        # Only refresh theme-dependent widgets when the theme actually changed
        if theme_changed:
            tag_panel = self._batch_ctrl.tag_panel
            if tag_panel is not None:
                tag_panel.refresh_theme()
            self._last_applied_theme = self._config.theme

        # 管理页标签面板仍按配置的分页大小展示（任务页已无分页）
        new_page_size = self._config.get("general", "page_size", default=20)
        tag_panel = self._batch_ctrl.tag_panel
        if tag_panel is not None:
            tag_panel.set_page_size(new_page_size)

        # Heatmap: repaint on colour-scheme change (refresh_tokens already called by app.py)
        if hasattr(self, "_heatmap_widget"):
            self._heatmap_widget.force_refresh()

        # Sync completed-last sort setting to repository
        if self._task_service.completed_last != self._config.sort_completed_last:
            self._task_service.completed_last = self._config.sort_completed_last
            data_changed = True

        # 阶段 5：置顶随配置即时生效；热键仅在已注册时重注册（避免测试占用系统热键）
        pinned = bool(self._config.get("general", "pin_on_top", default=False))
        self._window_shell.set_pinned(pinned)
        if hasattr(self, "_pin_btn"):
            self._pin_btn.setChecked(pinned)
        if self._window_shell.hotkey_registered:
            self._window_shell.install_hotkey()

        # Only reload task data when the sort order actually changed
        if data_changed:
            self._timeline_ctl.refresh()

        # 仅当默认分区的值真正发生变化时才切换（任何配置变更都跳回
        # 默认分区是错误行为——如切换主题/分页大小会无故丢失当前分区）
        default_pid = self._config.get("general", "default_partition", default="")
        if default_pid and default_pid != getattr(self, "_last_default_pid", ""):
            self._last_default_pid = default_pid
            current_pid = self._partition_ctrl.active_id or ""
            if default_pid != current_pid:
                self._partition_ctrl.activate(default_pid)

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
        if self._current_view != "edit":
            # 此前调用不存在的 _refresh_report 会在午夜崩溃（AttributeError）
            if hasattr(self, "_analysis_stats"):
                self._analysis_ctrl.refresh()
        if hasattr(self, "_timeline_ctl"):
            self._timeline_ctl.refresh()
        self._schedule_midnight_timer()
