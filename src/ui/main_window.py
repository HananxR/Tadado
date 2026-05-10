"""Main window — top-level QMainWindow with sidebar, task list, and heatmap."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
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
from ..models.task_status import TaskStatus
from ..services.md_formatter import MarkdownTaskFormatter
from ..services.md_parser import MarkdownTaskParser
from ..utils.signal_bus import get_signal_bus
from .calendar_heatmap.calendar_heatmap_widget import CalendarHeatmapWidget
from .dialogs.about_dialog import AboutDialog
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.task_dialog import TaskDialog
from .task_list.task_list_panel import TaskListPanel


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, config: AppConfig, repository: TaskRepository) -> None:
        super().__init__()
        self._config = config
        self._repository = repository
        self._signal_bus = get_signal_bus()

        self.setWindowTitle("DeskTodoSeq")
        self.resize(1100, 700)

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
        view_menu.addAction("切换热力图(&H)", self._on_toggle_heatmap)

        help_menu = menu_bar.addMenu("帮助(&H)")
        help_menu.addAction("关于(&A)", self._on_about)

    # ------------------------------------------------------------------
    # Tool bar
    # ------------------------------------------------------------------

    def _setup_tool_bar(self) -> None:
        toolbar = QToolBar("工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction("新建", self._on_new_task)
        toolbar.addAction("刷新", self._on_refresh)
        toolbar.addSeparator()
        toolbar.addAction("热力图", self._on_toggle_heatmap)

    # ------------------------------------------------------------------
    # Central widget
    # ------------------------------------------------------------------

    def _setup_central_widget(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        sidebar = self._build_sidebar()
        splitter.addWidget(sidebar)

        self._stack = QStackedWidget()

        # Page 0: Task list panel
        self._task_list_panel = TaskListPanel(self._repository)
        self._stack.addWidget(self._task_list_panel)

        # Page 1: Calendar heatmap
        self._heatmap_widget = CalendarHeatmapWidget(self._repository, self._config)
        self._heatmap_widget.date_selected.connect(self._on_date_selected)
        self._stack.addWidget(self._heatmap_widget)

        splitter.addWidget(self._stack)
        splitter.setSizes([220, 880])

        self.setCentralWidget(splitter)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(QLabel("快捷筛选"))
        self._btn_all = self._make_sidebar_button("全部任务")
        self._btn_today = self._make_sidebar_button("今日待办")
        self._btn_week = self._make_sidebar_button("本周任务")
        self._btn_overdue = self._make_sidebar_button("已逾期")
        layout.addWidget(self._btn_all)
        layout.addWidget(self._btn_today)
        layout.addWidget(self._btn_week)
        layout.addWidget(self._btn_overdue)

        layout.addSpacing(16)
        layout.addWidget(QLabel("状态统计"))
        self._status_list_label = QLabel("(加载中...)")
        layout.addWidget(self._status_list_label)

        layout.addStretch()
        return sidebar

    def _make_sidebar_button(self, text: str) -> QWidget:
        btn = QLabel(text)
        btn.setStyleSheet(
            "QLabel { padding: 4px 8px; border-radius: 4px; }"
            "QLabel:hover { background-color: rgba(128,128,128,0.15); }"
        )
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.mousePressEvent = lambda e, t=text: self._on_quick_filter(t)  # type: ignore[attr-defined]
        return btn

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
        bus.task_deleted.connect(self._on_data_changed)
        bus.task_status_changed.connect(self._on_data_changed)

    # ------------------------------------------------------------------
    # Slots: data
    # ------------------------------------------------------------------

    def _on_data_changed(self, *args) -> None:
        try:
            all_tasks = self._repository.get_all()
            due = self._repository.get_due_today()
            overdue = self._repository.get_overdue()
        except Exception:
            return
        self._status_total.setText(f"{len(all_tasks)} 个任务")
        self._status_due.setText(f"{len(due)} 个今日到期")
        self._status_overdue.setText(f"{len(overdue)} 个已逾期")
        self._update_sidebar_status_counts()
        if hasattr(self, '_heatmap_widget') and self._stack.currentIndex() == 1:
            self._heatmap_widget.refresh()

    def _update_sidebar_status_counts(self) -> None:
        try:
            counts = self._repository.get_status_counts()
        except Exception:
            return
        parts = []
        for status in (TaskStatus.URGENT, TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            c = counts.get(status, 0)
            if c > 0:
                parts.append(f"{status.display_name}: {c}")
        if not parts:
            self._status_list_label.setText("暂无任务")
        else:
            self._status_list_label.setText("  ".join(parts))

    # ------------------------------------------------------------------
    # Slots: task
    # ------------------------------------------------------------------

    def _on_new_task(self) -> None:
        dialog = TaskDialog(self._repository, parent=self)
        dialog.exec()

    def _on_quick_filter(self, label: str) -> None:
        preset_map = {
            "全部任务": "all",
            "今日待办": "today",
            "本周任务": "week",
            "已逾期": "overdue",
        }
        preset = preset_map.get(label, "all")
        if hasattr(self, '_task_list_panel'):
            self._task_list_panel.apply_preset_filter(preset)

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
        lines = []
        for task in tasks:
            if not task.archived:
                lines.append(formatter.format(task))

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
        if hasattr(self, '_task_list_panel'):
            self._task_list_panel.refresh()

    def _on_toggle_heatmap(self) -> None:
        current = self._stack.currentIndex()
        target = 1 if current == 0 else 0
        self._stack.setCurrentIndex(target)
        if target == 1 and hasattr(self, '_heatmap_widget'):
            self._heatmap_widget.refresh()

    def _on_about(self) -> None:
        dialog = AboutDialog(parent=self)
        dialog.exec()

    def _on_date_selected(self, selected_date: date) -> None:
        self._stack.setCurrentIndex(0)
        if hasattr(self, '_task_list_panel'):
            self._task_list_panel.apply_date_filter(selected_date)
