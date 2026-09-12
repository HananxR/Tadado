"""SelectionContext — 跨视图共享的选中上下文（分区 / 选中任务 / 时段粒度）。

视图之间不再互相触碰私有属性：读取当前状态、订阅 ``changed`` 信号即可。
Phase 1 仅接入分区；Phase 3/4 接入选中任务与时段。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class SelectionContext(QObject):
    """Shared selection state across pages."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._partition_id: str | None = None
        self._selected_task_id: str | None = None
        self._range: str = "week"  # week | month | 30d

    # ── 读取 ──

    @property
    def partition_id(self) -> str | None:
        return self._partition_id

    @property
    def selected_task_id(self) -> str | None:
        return self._selected_task_id

    @property
    def range(self) -> str:
        return self._range

    # ── 写入（同值不发射，避免无谓刷新） ──

    def set_partition(self, partition_id: str | None) -> None:
        if partition_id == self._partition_id:
            return
        self._partition_id = partition_id
        self.changed.emit()

    def select_task(self, task_id: str | None) -> None:
        if task_id == self._selected_task_id:
            return
        self._selected_task_id = task_id
        self.changed.emit()

    def set_range(self, range_: str) -> None:
        if range_ == self._range:
            return
        self._range = range_
        self.changed.emit()
