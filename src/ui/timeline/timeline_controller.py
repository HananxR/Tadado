"""TimelineController —— 任务页时间轴的数据编排。

职责：``TaskService`` → :class:`TimelineModel` → :class:`TimelineTableView`，
并把选中状态写入 :class:`SelectionContext`。总线事件走 50ms 去抖，避免
批量操作时重复查询。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from ...models.task_filter import TaskFilter
from ...services.task_service import TaskService
from ...utils.signal_bus import get_signal_bus
from ..selection_context import SelectionContext
from .timeline_gantt import TimelineTableView
from .timeline_model import RANGE_KEYS, TimelineData, TimelineModel


class TimelineController(QObject):
    """Drives the Gantt timeline view from the task service.

    Signals:
        task_selected(task_id): 选中变化（含清空时的空串）
        task_activated(task_id): 双击/右键请求打开任务
    """

    task_selected = Signal(str)
    task_activated = Signal(str)

    def __init__(
        self,
        task_service: TaskService,
        view: TimelineTableView,
        *,
        selection: SelectionContext | None = None,
        parent: QObject | None = None,
        refresh_interval_ms: int = 50,
    ) -> None:
        super().__init__(parent)
        self._svc = task_service
        self._view = view
        self._selection = selection
        self._model = TimelineModel()

        self._range_key = "week"
        self._sort_key = "deadline"
        self._statuses = None
        self._search_text = ""
        self._urgencies = None
        self._partition_id: str | None = None
        # 默认包含已归档任务：分区 archive_days=0 时「完成即归档」，若默认排除，
        # 任务一勾选完成就会从时间轴上消失。保留它可看到完成的任务（done 色条）。
        self._include_archived = True

        self._refresh_interval_ms = max(0, int(refresh_interval_ms))
        self._timer: QTimer | None = None
        self._visible = True
        self._dirty = False

        view.task_selected.connect(self._on_selected)
        view.task_activated.connect(self.task_activated.emit)

        bus = get_signal_bus()
        for signal in (
            bus.task_created,
            bus.task_updated,
            bus.task_deleted,
            bus.task_status_changed,
            bus.batch_operation_completed,
            bus.archive_completed,
            bus.tasks_bulk_created,
        ):
            signal.connect(self._on_bus_event)

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def set_range(self, range_key: str) -> None:
        if range_key not in RANGE_KEYS:
            raise ValueError(f"未知时间轴粒度: {range_key!r}")
        if range_key == self._range_key:
            return
        self._range_key = range_key
        self.refresh()

    def set_sort(self, sort_key: str) -> None:
        if sort_key == self._sort_key:
            return
        if sort_key not in TimelineModel.SORTS:
            raise ValueError(f"未知排序键: {sort_key!r}")
        self._sort_key = sort_key
        self.refresh()

    def set_filters(
        self,
        *,
        statuses=None,
        search_text: str | None = None,
        urgencies=None,
    ) -> None:
        """更新过滤条件并刷新。

        ``statuses`` / ``urgencies``：``None`` = 不过滤（每次调用都会覆盖）。
        ``search_text``：``None`` = 保持原值，避免输入过程中被清空。
        """
        self._statuses = statuses
        self._urgencies = urgencies
        if search_text is not None:
            self._search_text = search_text
        self.refresh()

    def set_partition(self, partition_id: str | None) -> None:
        self._partition_id = partition_id or None

    def set_include_archived(self, include: bool) -> None:
        self._include_archived = bool(include)
        self.refresh()

    @property
    def range_key(self) -> str:
        return self._range_key

    @property
    def sort_key(self) -> str:
        return self._sort_key

    # ------------------------------------------------------------------
    # 数据刷新
    # ------------------------------------------------------------------

    def refresh(self) -> TimelineData:
        """Query tasks and rebuild the timeline (immediate)."""
        filter_ = TaskFilter(partition_id=self._partition_id or None)
        if self._include_archived:
            filter_.show_archived = True
        tasks = self._svc.search(filter_)
        if not self._include_archived:
            # 仓库默认已排除归档；这里再兜底过滤一次（防御式）
            tasks = [t for t in tasks if not t.archived]
        data = self._model.build(
            tasks,
            self._range_key,
            statuses=self._statuses,
            search_text=self._search_text,
            urgencies=self._urgencies,
            sort_key=self._sort_key,
            include_archived=self._include_archived,
        )
        self._view.set_timeline(data)
        self._sync_selection()
        return data

    def _on_bus_event(self, *_args) -> None:
        self.schedule_refresh()

    def _ensure_timer(self) -> QTimer:
        if self._timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(self._refresh_interval_ms)
            timer.timeout.connect(self.refresh)
            self._timer = timer
        return self._timer

    def set_visible(self, visible: bool) -> None:
        """标记任务页是否在前台；不可见期间的刷新请求延后到再次可见时回放。"""
        self._visible = bool(visible)
        if self._visible and self._dirty:
            self._dirty = False
            self.refresh()

    @property
    def is_visible(self) -> bool:
        return self._visible

    @property
    def is_dirty(self) -> bool:
        """是否存在被延后、尚未执行的刷新。"""
        return self._dirty

    def schedule_refresh(self) -> None:
        """Coalesce rapid bus refreshes into one."""
        if not self._visible:
            self._dirty = True
            return
        if self._refresh_interval_ms <= 0:
            self.refresh()
            return
        self._ensure_timer().start()

    def flush_pending_refresh(self) -> None:
        """Run a pending coalesced refresh immediately (tests / shutdown)."""
        timer = self._timer
        if timer is not None and timer.isActive():
            timer.stop()
        if not self._visible:
            self._dirty = True
            return
        self.refresh()

    # ------------------------------------------------------------------
    # 选中
    # ------------------------------------------------------------------

    def _on_selected(self, task_id: str) -> None:
        if self._selection is not None:
            self._selection.select_task(task_id)
        self.task_selected.emit(task_id)

    def _sync_selection(self) -> None:
        """把 SelectionContext 中的任务重新高亮（数据刷新后保持选中）。"""
        if self._selection is None:
            return
        task_id = self._selection.selected_task_id
        if not task_id:
            return
        model = self._view.table_model
        for row in range(model.rowCount()):
            item = model.row_at(row)
            if item is not None and item.task_id == task_id:
                self._view.selectRow(row)
                return
