"""GraphController —— 「任务 + 分区」→ TaskGraphService → TaskGraphView。

总线事件 50ms 去抖；状态 chips / 仅看关联 / 隐藏已完成 / 分区切换均即时重算。
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from ...models.task_status import TaskStatus
from ...services.task_graph import TaskGraphService
from ...services.task_service import TaskService
from ...utils.signal_bus import get_signal_bus
from .graph_view import TaskGraphView

#: 状态 chips 键
FILTER_KEYS = ("all", "doing", "overdue", "week")


class GraphController(QObject):
    """Drives the task graph view.

    Signals:
        task_activated(task_id): 双击任务节点
    """

    task_activated = Signal(str)

    def __init__(
        self,
        task_service: TaskService,
        view: TaskGraphView,
        *,
        parent: QObject | None = None,
        refresh_interval_ms: int = 50,
    ) -> None:
        super().__init__(parent)
        self._svc = task_service
        self._view = view
        self._builder = TaskGraphService()

        self._filter = "all"
        self._only_related = False
        self._hide_done = False
        self._partition_id: str | None = None

        self._refresh_interval_ms = max(0, int(refresh_interval_ms))
        self._timer: QTimer | None = None

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
            bus.partitions_changed,
        ):
            signal.connect(self._on_bus_event)

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    @property
    def filter_key(self) -> str:
        return self._filter

    def set_filter(self, key: str) -> None:
        if key not in FILTER_KEYS:
            raise ValueError(f"未知图谱过滤键: {key!r}")
        if key == self._filter:
            return
        self._filter = key
        self.refresh()

    def set_only_related(self, enabled: bool) -> None:
        self._only_related = bool(enabled)
        self.refresh()

    def set_hide_done(self, enabled: bool) -> None:
        self._hide_done = bool(enabled)
        self.refresh()

    def set_partition(self, partition_id: str | None) -> None:
        self._partition_id = partition_id or None

    def relayout(self) -> None:
        """「重新布局」——换一个确定性变体。"""
        self._view.relayout()

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------

    def _matching_tasks(self):
        tasks = [t for t in self._svc.get_all() if not t.archived]
        if self._partition_id:
            tasks = [t for t in tasks if t.partition_id == self._partition_id]

        if self._filter == "doing":
            tasks = [t for t in tasks if t.status == TaskStatus.DOING]
        elif self._filter == "overdue":
            tasks = [t for t in tasks if t.status == TaskStatus.OVERDUE]
        elif self._filter == "week":
            monday = date.today() - timedelta(days=date.today().isoweekday() - 1)
            sunday = monday + timedelta(days=6)

            def in_week(task) -> bool:
                for d in (task.deadline_date, task.scheduled_date):
                    if d is not None and monday <= d <= sunday:
                        return True
                return False

            tasks = [t for t in tasks if in_week(t)]
        return tasks

    def refresh(self):
        """Rebuild the graph (immediate) and return ``(nodes, edges)``."""
        tasks = self._matching_tasks()
        partitions = self._svc.get_all_partitions()
        nodes, edges = self._builder.build_graph(
            tasks,
            partitions,
            hide_done=self._hide_done,
            only_related=self._only_related,
        )
        self._view.set_graph(nodes, edges)
        return nodes, edges

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

    def schedule_refresh(self) -> None:
        if self._refresh_interval_ms <= 0:
            self.refresh()
            return
        self._ensure_timer().start()

    def flush_pending_refresh(self) -> None:
        timer = self._timer
        if timer is not None and timer.isActive():
            timer.stop()
            self.refresh()


__all__ = ["FILTER_KEYS", "GraphController"]
