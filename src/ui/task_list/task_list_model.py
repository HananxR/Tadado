"""QAbstractTableModel wrapping a list of Task objects for display in QTableView."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from ...models.priority import Priority
from ...models.task import Task
from ...models.task_status import TaskStatus

_COLUMN_HEADERS = ["", "状态", "优先级", "标题", "截止日", "标签"]


class TaskListModel(QAbstractTableModel):
    """6-column table model: checkbox, status, priority, title, deadline, tags."""

    task_checked = Signal(str)  # task_id when checkbox toggled

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tasks: list[Task] = []

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tasks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else 6

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        task = self._tasks[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_data(task, col)

        if role == Qt.ItemDataRole.CheckStateRole and col == 0:
            return Qt.CheckState.Checked if task.status == TaskStatus.DONE else Qt.CheckState.Unchecked

        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground_color(task, col)

        if role == Qt.ItemDataRole.UserRole:
            return task

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment(col)

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            self.task_checked.emit(self._tasks[index.row()].id)
            return True
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags  # type: ignore[return-value]

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

    def remove_task(self, task_id: str) -> bool:
        for i, t in enumerate(self._tasks):
            if t.id == task_id:
                self.beginRemoveRows(QModelIndex(), i, i)
                del self._tasks[i]
                self.endRemoveRows()
                return True
        return False

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

    def task_ids(self) -> list[str]:
        return [t.id for t in self._tasks]

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _display_data(task: Task, col: int) -> str:
        if col == 0:
            return ""
        if col == 1:
            return task.status.display_name
        if col == 2:
            return task.priority.display_tag
        if col == 3:
            return task.title
        if col == 4:
            return task.deadline_date.isoformat() if task.deadline_date else ""
        if col == 5:
            return " ".join(f"#{t}" for t in task.tags)
        return ""

    @staticmethod
    def _foreground_color(task: Task, col: int) -> QColor | None:
        if col == 1:
            c = task.status.display_color
        elif col == 2 and task.priority != Priority.NONE:
            c = task.priority.display_color
        else:
            return None
        return QColor(c)

    @staticmethod
    def _alignment(col: int) -> Qt.AlignmentFlag:
        if col in (0, 1, 2, 4):
            return Qt.AlignmentFlag.AlignCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
