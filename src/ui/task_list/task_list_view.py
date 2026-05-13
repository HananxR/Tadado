"""QTableView for displaying tasks with context menu (no inline checkbox)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QMenu,
    QMessageBox,
    QTableView,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.md_formatter import MarkdownTaskFormatter
from ...utils.signal_bus import get_signal_bus
from ..dialogs.task_dialog import TaskDialog
from .task_list_delegate import TaskListDelegate
from .task_list_model import TaskListModel


class TaskListView(QTableView):
    """Table view of tasks with right-click context menu. No inline checkbox."""

    task_selected = Signal(Task)
    detail_requested = Signal(Task)

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._formatter = MarkdownTaskFormatter()

        self.setObjectName("taskListView")
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.setShowGrid(False)

        delegate = TaskListDelegate(self)
        self.setItemDelegate(delegate)

        self.customContextMenuRequested.connect(self._show_context_menu)
        self.clicked.connect(self._on_clicked)
        self.doubleClicked.connect(self._on_double_clicked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_task(self) -> Task | None:
        idx = self.currentIndex()
        if idx.isValid():
            return idx.data(Qt.ItemDataRole.UserRole)
        return None

    def set_model(self, model: TaskListModel) -> None:
        self.setModel(model)
        model.modelReset.connect(self._apply_column_widths)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._apply_column_widths()

    def _apply_column_widths(self) -> None:
        """6 columns: created, content, deadline, priority, status, tags."""
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(0, 130)   # 创建时间
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 任务内容
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(2, 105)   # 截止时间
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(3, 50)    # 优先级
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(4, 60)    # 状态
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)  # 标签
        if h.sectionSize(5) > 130:
            h.resizeSection(5, 110)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        if not index.isValid():
            return
        task: Task = index.data(Qt.ItemDataRole.UserRole)
        if task is None:
            return

        menu = QMenu(self)

        edit_action = menu.addAction("编辑(&E)")
        detail_action = menu.addAction("详情(&V)")
        delete_action = menu.addAction("删除(&D)")
        menu.addSeparator()

        status_menu = menu.addMenu("更改状态")
        for s in TaskStatus:
            action = status_menu.addAction(f"  {s.display_name}")
            action.setCheckable(True)
            action.setChecked(s == task.status)
            action.setData(s)
            action.triggered.connect(
                lambda checked=False, st=s, t=task: self._on_change_status(t, st)
            )

        menu.addSeparator()
        copy_action = menu.addAction("复制 MD(&C)")

        action = menu.exec(self.viewport().mapToGlobal(pos))

        if action == edit_action:
            self._on_edit_task(task)
        elif action == detail_action:
            self._on_detail_task(task)
        elif action == delete_action:
            self._on_delete_task(task)
        elif action == copy_action:
            QApplication.clipboard().setText(task.raw_md)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_clicked(self, index: QModelIndex) -> None:
        task = self.selected_task()
        if task:
            self.task_selected.emit(task)

    def _on_selection_changed(self) -> None:
        task = self.selected_task()
        if task:
            self.task_selected.emit(task)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        task: Task | None = index.data(Qt.ItemDataRole.UserRole)
        if task:
            self._on_edit_task(task)

    def _on_edit_task(self, task: Task) -> None:
        dialog = TaskDialog(self._repository, task=task, parent=self)
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            pass

    def _on_detail_task(self, task: Task) -> None:
        self.detail_requested.emit(task)

    def _on_delete_task(self, task: Task) -> None:
        result = QMessageBox.question(
            self,
            "确认删除",
            f'确定要删除任务 "{task.title}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._repository.delete(task.id)
            self._signal_bus.task_deleted.emit(task.id)

    def _on_change_status(self, task: Task, new_status: TaskStatus) -> None:
        old_status = task.status
        if old_status == new_status:
            return
        task.status = new_status
        if new_status == TaskStatus.DONE:
            task.completed_at = task.deadline_date or datetime.now()
        task.raw_md = self._formatter.format(task)
        task.updated_at = datetime.now()
        # Record in activity log
        task.activity_log.append({
            "ts": datetime.now().isoformat(),
            "content": f"状态变更: {old_status.display_name} → {new_status.display_name}",
        })
        self._repository.update(task)
        self._signal_bus.task_status_changed.emit(task, old_status)
