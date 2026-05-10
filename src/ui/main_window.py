"""Main window — Todoseq-style: input+filter at top, task list left, editor right."""

from __future__ import annotations

import datetime as dt
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
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
from ..models.repository import TaskRepository
from ..models.task import Task
from ..models.task_filter import TaskFilter
from ..models.task_status import TaskStatus
from ..services.md_formatter import MarkdownTaskFormatter
from ..services.md_parser import MarkdownTaskParser
from ..utils.signal_bus import get_signal_bus
from .calendar_heatmap.calendar_heatmap_widget import CalendarHeatmapWidget
from .dialogs.about_dialog import AboutDialog
from .dialogs.settings_dialog import SettingsDialog
from .task_list.task_edit_panel import TaskEditPanel
from .task_list.task_list_model import TaskListModel
from .task_list.task_list_view import TaskListView
from .widgets.filter_bar import FilterBar
from .widgets.task_input import TaskInputWidget


class MainWindow(QMainWindow):
    """Todoseq-style layout: input bar, filter bar, task list + edit panel."""

    def __init__(self, config: AppConfig, repository: TaskRepository) -> None:
        super().__init__()
        self._config = config
        self._repository = repository
        self._signal_bus = get_signal_bus()

        self.setWindowTitle("DeskTodoSeq")
        self.resize(1050, 680)

        self._setup_menu_bar()
        self._setup_tool_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction("导入 Markdown...(&I)", self._on_import)
        file_menu.addAction("导出 Markdown...(&E)", self._on_export)
        file_menu.addSeparator()
        file_menu.addAction("设置(&S)", self._on_settings)
        file_menu.addSeparator()
        file_menu.addAction("退出(&Q)", self._on_quit)

        view_menu = menu_bar.addMenu("视图(&V)")
        view_menu.addAction("刷新(&R)", self._on_refresh)
        view_menu.addSeparator()
        view_menu.addAction("热力图(&H)", self._on_toggle_heatmap)

        help_menu = menu_bar.addMenu("帮助(&H)")
        help_menu.addAction("关于(&A)", self._on_about)

    # ------------------------------------------------------------------
    # Tool bar
    # ------------------------------------------------------------------

    def _setup_tool_bar(self) -> None:
        toolbar = QToolBar("工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction("刷新", self._on_refresh)
        toolbar.addAction("热力图", self._on_toggle_heatmap)
        toolbar.addSeparator()
        toolbar.addAction("导入", self._on_import)
        toolbar.addAction("导出", self._on_export)
        toolbar.addSeparator()
        toolbar.addAction("设置", self._on_settings)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        # Stacked widget to switch between task view and heatmap
        self._stack = QStackedWidget()

        # --- Page 0: Task view (input + filter + [task list | edit panel]) ---
        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(8, 8, 8, 8)
        task_layout.setSpacing(6)

        # Quick actions row: input + quick filter buttons
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._input = TaskInputWidget(self._repository)
        input_row.addWidget(self._input, 1)

        filters = [
            ("全部", "all"),
            ("今日", "today"),
            ("本周", "week"),
            ("逾期", "overdue"),
        ]
        for label, preset in filters:
            btn = QPushButton(label)
            btn.setFixedWidth(50)
            btn.setStyleSheet(
                "QPushButton { padding: 4px 6px; font-size: 12px;"
                " border: 1px solid #ccc; border-radius: 4px; }"
                "QPushButton:hover { background: #e0e0e0; }"
            )
            btn.clicked.connect(lambda checked=False, p=preset: self._on_preset_filter(p))
            input_row.addWidget(btn)

        task_layout.addLayout(input_row)

        # Filter bar
        self._filter_bar = FilterBar()
        task_layout.addWidget(self._filter_bar)

        # Split: task list (left) + edit panel (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Left: task list
        self._task_model = TaskListModel()
        self._task_view = TaskListView(self._repository)
        self._task_view.set_model(self._task_model)
        self._task_view.task_selected.connect(self._on_task_selected)
        splitter.addWidget(self._task_view)

        # Right: edit panel + status counts
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._edit_panel = TaskEditPanel(self._repository)
        right_layout.addWidget(self._edit_panel)

        # Status counts
        self._status_label = QLabel("(加载中...)")
        self._status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        right_layout.addWidget(self._status_label)

        splitter.addWidget(right_panel)
        splitter.setSizes([700, 300])

        task_layout.addWidget(splitter, 1)
        self._stack.addWidget(task_page)

        # --- Page 1: Calendar heatmap ---
        self._heatmap_widget = CalendarHeatmapWidget(self._repository, self._config)
        self._heatmap_widget.date_selected.connect(self._on_date_selected)
        self._stack.addWidget(self._heatmap_widget)

        self.setCentralWidget(self._stack)

        # Initial load
        self._refresh_task_list()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _setup_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self._status_total = QLabel("0 个任务")
        self._status_due = QLabel("0 个今日到期")
        self._status_overdue = QLabel("0 个已逾期")
        self._status_bar.addWidget(self._status_total)
        self._status_bar.addWidget(self._status_due)
        self._status_bar.addWidget(self._status_overdue)
        self.setStatusBar(self._status_bar)

    def _connect_signals(self) -> None:
        bus = self._signal_bus
        bus.scan_completed.connect(self._on_data_changed)
        bus.task_created.connect(self._on_data_changed)
        bus.task_updated.connect(self._on_data_changed)
        bus.task_deleted.connect(self._on_task_deleted)
        bus.task_status_changed.connect(self._on_data_changed)
        self._filter_bar.filter_changed.connect(self._on_filter_changed)

    # ------------------------------------------------------------------
    # Slots: data
    # ------------------------------------------------------------------

    def _on_data_changed(self, *args) -> None:
        try:
            all_tasks = self._repository.get_all()
            due = self._repository.get_due_today()
            overdue = self._repository.get_overdue()
            counts = self._repository.get_status_counts()
        except Exception:
            return
        self._status_total.setText(f"{len(all_tasks)} 个任务")
        self._status_due.setText(f"{len(due)} 个今日到期")
        self._status_overdue.setText(f"{len(overdue)} 个已逾期")
        self._update_status_counts(counts)
        self._refresh_task_list()

    def _on_task_deleted(self, task_id: str) -> None:
        # If the deleted task is currently being edited, clear the editor
        if self._edit_panel.current_task() and self._edit_panel.current_task().id == task_id:
            self._edit_panel.clear()
        self._on_data_changed()

    def _update_status_counts(self, counts: dict[TaskStatus, int]) -> None:
        parts = []
        for s in (TaskStatus.URGENT, TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            c = counts.get(s, 0)
            if c > 0:
                parts.append(f"{s.display_name}: {c}")
        if not parts:
            self._status_label.setText("暂无任务")
        else:
            self._status_label.setText("  ".join(parts))

    def _refresh_task_list(self) -> None:
        filter_ = self._filter_bar.build_filter()
        tasks = self._repository.search(filter_)
        self._task_model.load_tasks(tasks)

    # ------------------------------------------------------------------
    # Slots: task interaction
    # ------------------------------------------------------------------

    def _on_filter_changed(self, filter_) -> None:
        self._refresh_task_list()
        self._edit_panel.clear()

    def _on_task_selected(self, task: Task) -> None:
        self._edit_panel.load_task(task)

    def _on_preset_filter(self, preset: str) -> None:
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
        self._on_data_changed()

    def _on_toggle_heatmap(self) -> None:
        current = self._stack.currentIndex()
        target = 1 if current == 0 else 0
        self._stack.setCurrentIndex(target)
        if target == 1:
            self._heatmap_widget.refresh()

    def _on_about(self) -> None:
        dialog = AboutDialog(parent=self)
        dialog.exec()

    def _on_date_selected(self, selected_date: date) -> None:
        self._stack.setCurrentIndex(0)
        self._filter_bar.blockSignals(True)
        self._filter_bar.reset()
        self._filter_bar.blockSignals(False)
        self._filter_bar.filter_changed.emit(
            TaskFilter(date_from=selected_date, date_to=selected_date)
        )
