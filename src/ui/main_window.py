"""Main window — Todoseq-style layout with stats bar, carousel, and adaptive sizing."""

from __future__ import annotations

import datetime as dt
from datetime import date

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..models.priority import Priority
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

        self.setWindowTitle("DeskTodoSeq")

        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._connect_signals()
        self._setup_shortcuts()

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
        self.setMinimumSize(800, 500)
        self.resize(w, h)
        self.move(
            (geom.width() - w) // 2 + geom.x(),
            (geom.height() - h) // 2 + geom.y(),
        )

    def _apply_splitter_sizes(self) -> None:
        """Lock splitter to 65/35 proportion based on current width."""
        if self._splitter is None:
            return
        total = self._splitter.width()
        if total > 100:
            self._splitter.setSizes([int(total * 0.65), int(total * 0.35)])

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

    def _setup_tool_bar(self) -> None:
        toolbar = QToolBar("导航")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22, 22))
        self.addToolBar(toolbar)

        # Logo button — click returns to main task view
        logo_action = QAction(load_icon("app"), "主页", self)
        logo_action.setToolTip("返回主界面")
        logo_action.triggered.connect(self._on_go_home)
        toolbar.addAction(logo_action)

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
        task_layout.addWidget(self._filter_bar)

        # Row 4: Status statistics bar
        self._stats_bar = StatusStatsBar(self._repository)
        self._stats_bar.filter_changed.connect(self._on_stats_filter)
        task_layout.addWidget(self._stats_bar)

        # Row 5: Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #e0ddd6;")
        task_layout.addWidget(sep)

        # Row 6: Splitter (task list | edit panel)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(False)

        # Left: task list
        self._task_model = TaskListModel()
        self._task_view = TaskListView(self._repository)
        self._task_view.set_model(self._task_model)
        self._task_view.task_selected.connect(self._on_task_selected)
        self._task_view.detail_requested.connect(self._on_detail_requested)
        self._splitter.addWidget(self._task_view)

        # Right: edit panel
        self._edit_panel = TaskEditPanel(self._repository)
        self._edit_panel.setMinimumWidth(260)
        self._splitter.addWidget(self._edit_panel)

        task_layout.addWidget(self._splitter, 1)
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

        self._carousel.set_items(
            [{"task_id": "", "text": "今日无事，找点事情干一下吧 ☕", "color": "#aaa"}]
        )
        self.setCentralWidget(self._stack)
        self._refresh_task_list()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self._status_total = QLabel()
        self._status_due = QLabel()
        self._status_overdue = QLabel()
        self._status_bar.addWidget(self._status_total)
        self._status_bar.addWidget(self._status_due)
        self._status_bar.addWidget(self._status_overdue)
        self.setStatusBar(self._status_bar)

    # ------------------------------------------------------------------
    # Signals & shortcuts
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        bus = self._signal_bus
        bus.scan_completed.connect(self._on_data_changed)
        bus.task_created.connect(self._on_data_changed)
        bus.task_updated.connect(self._on_data_changed)
        bus.task_deleted.connect(self._on_task_deleted)
        bus.task_status_changed.connect(self._on_data_changed)
        self._filter_bar.filter_changed.connect(self._on_filter_changed)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_task)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_refresh)
        QShortcut(QKeySequence("Ctrl+H"), self, activated=self._on_toggle_heatmap)
        QShortcut(QKeySequence("Escape"), self, activated=self._edit_panel.clear)

    # ------------------------------------------------------------------
    # Slots: data refresh
    # ------------------------------------------------------------------

    def _on_data_changed(self, *args) -> None:
        self._update_status_labels()
        self._refresh_task_list()
        self._stats_bar.refresh()
        today = date.today()
        self._update_carousel(TaskFilter(date_from=today, date_to=today))

    def _update_status_labels(self) -> None:
        """Refresh the bottom status bar totals."""
        try:
            all_tasks = self._repository.get_all()
            due = self._repository.get_due_today()
            overdue = self._repository.get_overdue()
        except Exception:
            return
        self._status_total.setText(f"{len(all_tasks)} 个任务")
        self._status_due.setText(f"{len(due)} 个今日到期")
        self._status_overdue.setText(f"{len(overdue)} 个已逾期")

    def _on_task_deleted(self, task_id: str) -> None:
        if self._edit_panel.current_task() and self._edit_panel.current_task().id == task_id:
            self._edit_panel.clear()
        self._on_data_changed()

    def _refresh_task_list(self, filter_: TaskFilter | None = None) -> None:
        if filter_ is None:
            filter_ = self._filter_bar.build_filter()
        tasks = self._repository.search(filter_)
        self._task_model.load_tasks(tasks)
        self._auto_select_first()

    def _auto_select_first(self) -> None:
        """Auto-select the first (most important) task in the current list.
        If the list is empty, show an encouraging empty-state message."""
        all_tasks = self._task_model.tasks
        if not all_tasks:
            self._edit_panel.show_empty()
            return

        # Sort: status importance → priority → closest deadline
        status_rank = {
            TaskStatus.URGENT: 0, TaskStatus.TODO: 1, TaskStatus.DOING: 2,
            TaskStatus.WAIT: 3, TaskStatus.LATER: 4, TaskStatus.DONE: 5,
        }
        priority_rank = {"A": 0, "B": 1, "C": 2, "D": 3}
        sorted_tasks = sorted(
            all_tasks,
            key=lambda t: (
                status_rank.get(t.status, 99),
                priority_rank.get(t.priority.name, 99),
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

    def _update_carousel(self, filter_: TaskFilter | None = None) -> None:
        if filter_ is not None:
            tasks = self._repository.search(filter_)
        else:
            tasks = self._repository.get_all()

        active = [t for t in tasks if t.status != TaskStatus.DONE]
        done = [t for t in tasks if t.status == TaskStatus.DONE]

        items: list[dict] = []
        for t in active:
            if t.priority in (Priority.A, Priority.B):
                items.append({
                    "task_id": t.id,
                    "text": f"[{t.priority.name}] {t.title}",
                    "color": t.status.display_color,
                })
        for t in done:
            items.append({
                "task_id": t.id,
                "text": f"✓ {t.title}",
                "color": "#27ae60",
            })
        for t in active:
            if t.priority not in (Priority.A, Priority.B):
                items.append({
                    "task_id": t.id,
                    "text": f"· {t.title}",
                    "color": "#888",
                })

        if not items:
            items = [{"task_id": "", "text": "今日无事，找点事情干一下吧 ☕", "color": "#aaa"}]
        self._carousel.set_items(items[:10])

    # ------------------------------------------------------------------
    # Slots: filters
    # ------------------------------------------------------------------

    def _on_filter_changed(self, filter_: TaskFilter) -> None:
        if not self._guard_draft():
            return
        self._update_status_labels()
        self._edit_panel.clear()
        self._refresh_task_list(filter_)
        self._stats_bar.refresh()
        self._update_carousel(filter_)

    def _on_stats_filter(self, filter_: TaskFilter) -> None:
        if not self._guard_draft():
            return
        self._filter_bar.blockSignals(True)
        self._filter_bar.reset()
        self._filter_bar.blockSignals(False)
        tasks = self._repository.search(filter_)
        self._task_model.load_tasks(tasks)
        self._update_status_labels()
        self._edit_panel.clear()
        self._auto_select_first()
        self._stats_bar.refresh()
        self._update_carousel(filter_)

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
        self._filter_bar.filter_changed.emit(TaskFilter())
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
        today = date.today()
        self._filter_bar.reset()

        if preset == "all":
            self._filter_bar.filter_changed.emit(TaskFilter())
        elif preset == "today":
            self._filter_bar.filter_changed.emit(TaskFilter(date_from=today, date_to=today))
        elif preset == "week":
            weekday = today.isoweekday()
            monday = today - dt.timedelta(days=weekday - 1)
            sunday = monday + dt.timedelta(days=6)
            self._filter_bar.filter_changed.emit(TaskFilter(date_from=monday, date_to=sunday))
        elif preset == "overdue":
            self._filter_bar.filter_changed.emit(TaskFilter(overdue_only=True))

    def _on_new_task(self) -> None:
        """Ctrl+N — same as clicking the '新建' toolbar button."""
        self._on_new_draft()

    def _on_new_draft(self) -> None:
        """Create a draft TODO task under today's filter view."""
        if not self._guard_draft():
            return
        today = date.today()
        self._filter_bar.filter_changed.emit(TaskFilter(date_from=today, date_to=today))
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
                task = Task(
                    id="",
                    raw_md=raw_line,
                    title=parsed.title,
                    status=parsed.status,
                    priority=parsed.priority,
                    tags=parsed.tags,
                    scheduled_date=parsed.scheduled_date,
                    deadline_date=parsed.deadline_date,
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
        dialog = SettingsDialog(self._config, parent=self)
        dialog.exec()
        self._signal_bus.config_changed.emit()

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
        self._filter_bar.filter_changed.emit(
            TaskFilter(date_from=selected_date, date_to=selected_date)
        )
