"""QAbstractTableModel wrapping a list of Task objects for display in QTableView."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont as QtFont

from ...models.priority import Priority
from ...models.task import Task
from ...models.task_status import TaskStatus

_COLUMN_HEADERS = ["#", "创建时间", "任务内容", "截止时间", "优先级", "状态"]

COL_ROW = 0
COL_CREATED = 1
COL_CONTENT = 2
COL_DEADLINE = 3
COL_PRIORITY = 4
COL_STATUS = 5


class TaskListModel(QAbstractTableModel):
    """7-column table: row#, created, content, deadline, priority, status, tags."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tasks: list[Task] = []
        self._offset: int = 0

    def set_offset(self, offset: int) -> None:
        self._offset = offset

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tasks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMN_HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        task = self._tasks[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_ROW:
                return str(self._offset + index.row() + 1)
            return self._display_data(task, col)

        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground_color(task, col)

        if role == Qt.ItemDataRole.FontRole:
            if col == COL_CONTENT:
                return QtFont("Consolas", 10)
            if col in (COL_CREATED, COL_DEADLINE):
                return QtFont("Consolas", 9)

        if role == Qt.ItemDataRole.UserRole:
            return task

        if role == Qt.ItemDataRole.BackgroundRole:
            return self._background_color(task)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment(col)

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_CONTENT:
                return task.raw_md
            if col == COL_CREATED and task.created_at:
                return task.created_at.strftime("%Y-%m-%d %H:%M")

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable  # type: ignore[return-value]

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(_COLUMN_HEADERS):
                return _COLUMN_HEADERS[section]
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def task_at(self, row: int) -> Task:
        return self._tasks[row]

    def load_tasks(self, tasks: list[Task]) -> None:
        self.beginResetModel()
        self._tasks = tasks
        self.endResetModel()

    def insert_task(self, task: Task) -> None:
        row = len(self._tasks)
        self.beginInsertRows(QModelIndex(), row, row)
        self._tasks.append(task)
        self.endInsertRows()

    def update_task(self, task: Task) -> None:
        for i, t in enumerate(self._tasks):
            if t.id == task.id:
                self._tasks[i] = task
                idx = self.index(i, 0)
                idx2 = self.index(i, self.columnCount() - 1)
                self.dataChanged.emit(idx, idx2)
                return

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _display_data(task: Task, col: int) -> str:
        if col == COL_CREATED:
            return task.created_at.strftime("%Y-%m-%d %H:%M") if task.created_at else ""
        if col == COL_CONTENT:
            return task.title or task.raw_md
        if col == COL_DEADLINE:
            d = task.deadline_date or task.scheduled_date
            return d.isoformat() if d else ""
        if col == COL_PRIORITY:
            if task.priority == Priority.NONE:
                return "—"
            return task.priority.name
        if col == COL_STATUS:
            return task.status.display_name
        return ""

    @staticmethod
    def _foreground_color(task: Task, col: int) -> QColor | None:
        if col == COL_STATUS:
            return QColor(task.status.display_color)
        if col == COL_PRIORITY and task.priority != Priority.NONE:
            return QColor(task.priority.display_color)
        return None

    @staticmethod
    def _background_color(task: Task) -> QColor | None:
        from datetime import date as _date
        today = _date.today()
        if task.status == TaskStatus.URGENT:
            return QColor("#fff0f0")
        if task.deadline_date and task.deadline_date < today and task.status != TaskStatus.DONE:
            return QColor("#fff8f0")
        return None

    @staticmethod
    def _alignment(col: int) -> Qt.AlignmentFlag:
        if col in (COL_ROW, COL_CREATED, COL_DEADLINE, COL_PRIORITY, COL_STATUS):
            return Qt.AlignmentFlag.AlignCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
