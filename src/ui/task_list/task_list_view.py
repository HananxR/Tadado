"""QTableView for displaying tasks with context menu and checkbox support."""

from __future__ import annotations

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
    """Table view of tasks with right-click context menu."""

    task_selected = Signal(Task)

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._signal_bus = get_signal_bus()
        self._formatter = MarkdownTaskFormatter()
        self._selected_task: Task | None = None

        self.setObjectName("taskListView")
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.setShowGrid(False)

        # Column widths
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().resizeSection(0, 30)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().resizeSection(1, 60)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().resizeSection(2, 50)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().resizeSection(4, 90)
        self.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().resizeSection(5, 120)

        # Model and delegate
        delegate = TaskListDelegate(self)
        self.setItemDelegate(delegate)

        # Connections
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
        model.task_checked.connect(self._on_checkbox_toggled)

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
        delete_action = menu.addAction("删除(&D)")
        menu.addSeparator()

        status_menu = menu.addMenu("更改状态")
        for s in TaskStatus:
            action = status_menu.addAction(s.display_name)
            action.setData(s)
            action.triggered.connect(
                lambda checked=False, st=s: self._on_change_status(task, st)
            )

        menu.addSeparator()
        copy_action = menu.addAction("复制 MD(&C)")

        action = menu.exec(self.viewport().mapToGlobal(pos))

        if action == edit_action:
            self._on_edit_task(task)
        elif action == delete_action:
            self._on_delete_task(task)
        elif action == copy_action:
            QApplication.clipboard().setText(task.raw_md)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_clicked(self, index: QModelIndex) -> None:
        if index.column() == 0:
            task: Task | None = index.data(Qt.ItemDataRole.UserRole)
            if task:
                self._toggle_task_status(task)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        task: Task | None = index.data(Qt.ItemDataRole.UserRole)
        if task:
            self._on_edit_task(task)

    def _on_checkbox_toggled(self, task_id: str) -> None:
        task = self._repository.get_by_id(task_id)
        if task:
            self._toggle_task_status(task)

    def _on_edit_task(self, task: Task) -> None:
        dialog = TaskDialog(self._repository, task=task, parent=self)
        if dialog.exec() == TaskDialog.DialogCode.Accepted:
            pass  # signal already emitted by TaskDialog

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
        task.status = new_status
        if new_status == TaskStatus.DONE:
            from datetime import datetime

            task.completed_at = datetime.now()
        task.raw_md = self._formatter.format(task)
        self._repository.update(task)
        self._signal_bus.task_status_changed.emit(task, old_status)

    def _toggle_task_status(self, task: Task) -> None:
        new_status = task.status.next_status
        self._on_change_status(task, new_status)
