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
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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

    def selected_task_ids(self) -> list[str]:
        """Return task IDs of all selected rows."""
        sm = self.selectionModel()
        if not sm:
            return []
        ids: list[str] = []
        for idx in sm.selectedRows():
            task = idx.data(Qt.ItemDataRole.UserRole)
            if task:
                ids.append(task.id)
        return ids

    def set_model(self, model: TaskListModel) -> None:
        self.setModel(model)
        model.modelReset.connect(self._apply_column_widths)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._apply_column_widths()

    def _apply_column_widths(self) -> None:
        """9 columns: checkbox(30), row#(30), created(80), content(Stretch), deadline(95), progress(45), status(55), tags(80), archived(55)."""
        from .task_list_model import COL_CHECK, COL_ROW, COL_CREATED, COL_CONTENT
        from .task_list_model import COL_DEADLINE, COL_PROGRESS, COL_STATUS, COL_TAGS, COL_ARCHIVED

        h = self.horizontalHeader()
        col_count = self.model().columnCount() if self.model() else 0
        h.setMinimumSectionSize(40)

        h.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_CHECK, 30)
        h.setSectionResizeMode(COL_ROW, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_ROW, 30)
        h.setSectionResizeMode(COL_CREATED, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_CREATED, 80)
        h.setSectionResizeMode(COL_CONTENT, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_DEADLINE, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_DEADLINE, 95)
        h.setSectionResizeMode(COL_PROGRESS, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_PROGRESS, 45)
        h.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_STATUS, 55)
        h.setSectionResizeMode(COL_TAGS, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(COL_TAGS, 80)
        if col_count > COL_ARCHIVED:
            h.setSectionResizeMode(COL_ARCHIVED, QHeaderView.ResizeMode.Fixed)
            h.resizeSection(COL_ARCHIVED, 55)

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
        for s in (TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            action = status_menu.addAction(f"  {s.display_name}")
            action.setData(s)
            action.setCheckable(True)
            action.setChecked(s == task.status)
            action.triggered.connect(
                lambda checked=False, st=s, t=task: self._on_change_status(t, st)
            )
        if task.status == TaskStatus.OVERDUE:
            locked_action = status_menu.addAction("  逾期 (不可更改)")
            locked_action.setEnabled(False)

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
        # Only emit task_selected for single-row selections (not batch)
        ids = self.selected_task_ids()
        if len(ids) == 1:
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
        from ..dialogs.timeline_detail_dialog import TimelineDetailDialog
        dlg = TimelineDetailDialog(task, self._repository, parent=self)
        dlg.exec()

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
        # OVERDUE is locked — cannot be manually changed
        if task.status == TaskStatus.OVERDUE:
            return
        old_status = task.status
        if old_status == new_status:
            return
        task.status = new_status
        if new_status == TaskStatus.DONE:
            task.completed_at = task.deadline_date or datetime.now()
        task.raw_md = self._formatter.format(task)
        task.updated_at = datetime.now()
        # Record in activity log
        if new_status == TaskStatus.DONE:
            task.activity_log.append({
                "ts": task.completed_at.isoformat() if task.completed_at else datetime.now().isoformat(),
                "content": f"任务完成 ✓ 截止: {task.deadline_date.isoformat()}" if task.deadline_date else "任务完成 ✓",
                "status": new_status.value,
            })
        else:
            task.activity_log.append({
                "ts": datetime.now().isoformat(),
                "content": f"状态变更: {old_status.display_name} → {new_status.display_name}",
                "status": new_status.value,
            })
        self._repository.update(task)
        self._signal_bus.task_status_changed.emit(task, old_status)
