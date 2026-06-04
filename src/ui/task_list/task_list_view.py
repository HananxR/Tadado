"""QTableView for displaying tasks with context menu (no inline checkbox)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
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

    # Batch operation signals (emitted from right-click menu)
    batch_status_change = Signal(list, object)  # list[task_id], TaskStatus
    batch_urgency_change = Signal(list, int)    # list[task_id], urgency
    batch_delete = Signal(list)                 # list[task_id]
    batch_suspend = Signal(list)                # list[task_id]
    batch_restart = Signal(list)                # list[task_id]
    batch_postpone = Signal(list, int)          # list[task_id], days

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
        self.setShowGrid(True)

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

    def _collect_target_ids(self, task: Task) -> list[str]:
        """Return target IDs: checked > row selection > clicked single."""
        model = self.model()
        if model is not None and hasattr(model, 'checked_task_ids'):
            checked = set(model.checked_task_ids())
            if task.id in checked and len(checked) > 1:
                return list(checked)
        # Fall back to row selection (Ctrl/Shift+Click multi-select)
        row_ids = self.selected_task_ids()
        if len(row_ids) > 1:
            return row_ids
        return [task.id]

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        if not index.isValid():
            return
        task: Task = index.data(Qt.ItemDataRole.UserRole)
        if task is None:
            return

        menu = QMenu(self)

        # ── 修改类操作 ──
        status_menu = menu.addMenu("更改状态")
        for s in (TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            action = status_menu.addAction(f"  {s.display_name}")
            action.setCheckable(True)
            action.setChecked(s == task.status)
            action.triggered.connect(
                lambda checked=False, st=s, t=task: self._emit_batch_status(t, st)
            )
        if task.status == TaskStatus.OVERDUE:
            locked_action = status_menu.addAction("  逾期 (不可更改)")
            locked_action.setEnabled(False)

        urgency_menu = menu.addMenu("更改优先级")
        _URGENCY_LABELS = [
            (0, "● 紧急"), (1, "● 重要"), (2, "● 关注"), (3, "● 普通"),
        ]
        for val, label in _URGENCY_LABELS:
            ua = urgency_menu.addAction(f"  {label}")
            ua.setCheckable(True)
            ua.setChecked(val == getattr(task, 'urgency', 3))
            ua.triggered.connect(
                lambda checked=False, v=val, t=task: self._emit_batch_urgency(t, v)
            )

        postpone_menu = menu.addMenu("延后处理")
        for days in [1, 2, 5, 7, 10]:
            postpone_menu.addAction(
                f"+{days}天", lambda d=days, t=task: self._emit_batch_postpone(t, d)
            )

        menu.addSeparator()

        # ── 终端操作（危险度递增）──
        menu.addAction("中止", lambda t=task: self._emit_batch_suspend(t))
        menu.addAction("重启", lambda t=task: self._emit_batch_restart(t))
        menu.addAction("删除", lambda t=task: self._emit_batch_delete(t))

        menu.exec(self.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Batch action emitters (collect IDs → emit signal)
    # ------------------------------------------------------------------

    def _emit_batch_status(self, task: Task, status: TaskStatus) -> None:
        ids = self._collect_target_ids(task)
        self.batch_status_change.emit(ids, status)

    def _emit_batch_urgency(self, task: Task, urgency: int) -> None:
        ids = self._collect_target_ids(task)
        self.batch_urgency_change.emit(ids, urgency)

    def _emit_batch_delete(self, task: Task) -> None:
        ids = self._collect_target_ids(task)
        self.batch_delete.emit(ids)

    def _emit_batch_suspend(self, task: Task) -> None:
        ids = self._collect_target_ids(task)
        self.batch_suspend.emit(ids)

    def _emit_batch_restart(self, task: Task) -> None:
        ids = self._collect_target_ids(task)
        self.batch_restart.emit(ids)

    def _emit_batch_postpone(self, task: Task, days: int) -> None:
        ids = self._collect_target_ids(task)
        self.batch_postpone.emit(ids, days)

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
