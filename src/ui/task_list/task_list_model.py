"""QAbstractTableModel wrapping a list of Task objects for display in QTableView."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont as QtFont

from ...models.task import Task
from ...models.task_status import TaskStatus

_COLUMN_HEADERS = ["", "#", "创建时间", "任务内容", "截止时间", "进度", "状态", "标签", "归档"]

COL_CHECK = 0
COL_ROW = 1
COL_CREATED = 2
COL_CONTENT = 3
COL_DEADLINE = 4
COL_PROGRESS = 5
COL_STATUS = 6
COL_TAGS = 7
COL_ARCHIVED = 8


class TaskListModel(QAbstractTableModel):
    """9-column table: checkbox, row#, created, content, deadline, progress, status, tags, archived."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tasks: list[Task] = []
        self._offset: int = 0
        self._checked_ids: set[str] = set()
        self._highlighted_task_id: str | None = None
        self._bold_task_ids: set[str] = set()

    def set_offset(self, offset: int) -> None:
        self._offset = offset

    def checked_task_ids(self) -> list[str]:
        return list(self._checked_ids)

    def set_checked_ids(self, ids: set[str]) -> None:
        self._checked_ids = set(ids)
        if self._tasks:
            top = self.index(0, COL_CHECK)
            bot = self.index(len(self._tasks) - 1, COL_CHECK)
            self.dataChanged.emit(top, bot, [Qt.ItemDataRole.CheckStateRole])

    def select_all(self) -> None:
        self._checked_ids = {t.id for t in self._tasks}
        if self._tasks:
            top = self.index(0, COL_CHECK)
            bot = self.index(len(self._tasks) - 1, COL_CHECK)
            self.dataChanged.emit(top, bot, [Qt.ItemDataRole.CheckStateRole])

    def deselect_all(self) -> None:
        self._checked_ids.clear()
        if self._tasks:
            top = self.index(0, COL_CHECK)
            bot = self.index(len(self._tasks) - 1, COL_CHECK)
            self.dataChanged.emit(top, bot, [Qt.ItemDataRole.CheckStateRole])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tasks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMN_HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        task = self._tasks[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.CheckStateRole and col == COL_CHECK:
            return Qt.CheckState.Checked if task.id in self._checked_ids else Qt.CheckState.Unchecked

        if role == Qt.ItemDataRole.DisplayRole:
            if col == COL_ROW:
                return str(self._offset + index.row() + 1)
            return self._display_data(task, col)

        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground_color(task, col)

        if role == Qt.ItemDataRole.FontRole:
            if col == COL_CONTENT:
                font = QtFont("Consolas", 9)
                if task.id == self._highlighted_task_id or task.id in self._bold_task_ids:
                    font.setBold(True)
                return font
            if col in (COL_CREATED, COL_DEADLINE):
                return QtFont("Consolas", 8)

        if role == Qt.ItemDataRole.UserRole:
            return task

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment(col)

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == COL_CONTENT:
                return task.raw_md
            if col == COL_CREATED and task.created_at:
                return task.created_at.strftime("%Y-%m-%d %H:%M")

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or index.column() != COL_CHECK:
            return False
        if role == Qt.ItemDataRole.CheckStateRole:
            task = self._tasks[index.row()]
            if value == Qt.CheckState.Checked:
                self._checked_ids.add(task.id)
            else:
                self._checked_ids.discard(task.id)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            return True
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if index.column() == COL_CHECK:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable  # type: ignore[return-value]
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

    def prepend_task(self, task: Task) -> None:
        """Insert task at position 0 (top of list)."""
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._tasks.insert(0, task)
        self.endInsertRows()

    def move_to_top(self, row: int) -> None:
        """Move task at given row to position 0."""
        if row <= 0:
            return
        self.beginMoveRows(QModelIndex(), row, row, QModelIndex(), 0)
        task = self._tasks.pop(row)
        self._tasks.insert(0, task)
        self.endMoveRows()

    def set_bold_tasks(self, task_ids: set[str]) -> None:
        """Mark tasks for bold rendering (multi-task batch members)."""
        self._bold_task_ids = task_ids
        if self._tasks:
            top = self.index(0, 0)
            bot = self.index(len(self._tasks) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bot)

    def highlighted_task_id(self) -> str | None:
        """Return the currently highlighted task ID (red+bold)."""
        return self._highlighted_task_id

    def set_highlighted_task(self, task_id: str | None) -> None:
        """Set the task to highlight in red+bold (first in list)."""
        self._highlighted_task_id = task_id
        if self._tasks:
            top = self.index(0, 0)
            bot = self.index(len(self._tasks) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bot)

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
            return task.created_at.strftime("%Y-%m-%d") if task.created_at else ""
        if col == COL_CONTENT:
            return task.title or task.raw_md
        if col == COL_DEADLINE:
            d = task.deadline_date or task.scheduled_date
            return d.isoformat() if d else ""
        if col == COL_PROGRESS:
            return TaskListModel._calc_progress(task)
        if col == COL_STATUS:
            return task.status.display_name
        if col == COL_TAGS:
            return " ".join(f"#{t}" for t in task.tags)
        if col == COL_ARCHIVED:
            if task.status == TaskStatus.DONE:
                return "已归档" if task.archived else "未归档"
            return "/"
        return ""

    def _foreground_color(self, task: Task, col: int) -> QColor | None:
        if col == COL_CONTENT and task.id == self._highlighted_task_id:
            return QColor("red")
        if col == COL_STATUS:
            return QColor(task.status.display_color)
        return None

    @staticmethod
    def _urgency_color(urgency: int) -> QColor:
        """Return the dot color for a given urgency level (0-3)."""
        from ...utils.design_tokens import get_tokens
        t = get_tokens()
        if urgency == 0:
            return QColor(t.urgency_urgent)
        elif urgency == 1:
            return QColor(t.urgency_high)
        elif urgency == 2:
            return QColor(t.urgency_medium)
        else:
            return QColor(t.text_secondary)  # hollow gray dot for 普通

    @staticmethod
    def _calc_progress(task: Task) -> str:
        """Progress 0-100% from Task.progress field (manually set by user)."""
        return f"{task.progress}%"

    @staticmethod
    def _alignment(col: int) -> Qt.AlignmentFlag:
        if col in (COL_CHECK, COL_ROW, COL_CREATED, COL_DEADLINE, COL_PROGRESS, COL_STATUS, COL_ARCHIVED):
            return Qt.AlignmentFlag.AlignCenter
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    # ------------------------------------------------------------------
    # Internal helpers (continued)
    # ------------------------------------------------------------------
