"""TimelineTableView / TimelineTableModel / TimelineController 测试（离线渲染）。"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from src.models.repository import TaskRepository
from src.models.task import Task
from src.models.task_status import TaskStatus
from src.services.task_service import TaskService
from src.ui.selection_context import SelectionContext
from src.ui.timeline import (
    TimelineController,
    TimelineTableModel,
    TimelineTableView,
    axis_cell_width,
)
from src.ui.timeline.timeline_model import TimelineModel
from src.utils.signal_bus import get_signal_bus

TODAY = date(2026, 9, 12)


def make_task(
    task_id: str,
    title: str,
    *,
    status: TaskStatus = TaskStatus.TODO,
    progress: int = 0,
    scheduled_date: date | None = None,
    deadline_date: date | None = None,
    partition_id: str | None = None,
) -> Task:
    return Task(
        id=task_id,
        raw_md=f"- [ ] {title}",
        title=title,
        status=status,
        progress=progress,
        scheduled_date=scheduled_date,
        deadline_date=deadline_date,
        partition_id=partition_id,
        created_at=datetime.combine(TODAY, datetime.min.time()),
    )


def _sample_data():
    tasks = [
        make_task("a", "重构认证", status=TaskStatus.DOING, progress=60,
                  scheduled_date=date(2026, 9, 8), deadline_date=date(2026, 9, 11)),
        make_task("b", "补测试", scheduled_date=date(2026, 9, 12),
                  deadline_date=date(2026, 9, 13)),
    ]
    return TimelineModel().build(tasks, "week", TODAY)


# ---------------------------------------------------------------------------
# 纯几何
# ---------------------------------------------------------------------------


class TestAxisCellWidth:
    def test_basic(self):
        assert axis_cell_width(700, 7) == pytest.approx(100.0)

    def test_guards_zero(self):
        assert axis_cell_width(700, 0) == 0.0
        assert axis_cell_width(0, 7) == 1.0


# ---------------------------------------------------------------------------
# 表格模型
# ---------------------------------------------------------------------------


class TestTimelineTableModel:
    def test_empty_by_default(self, qapp):
        model = TimelineTableModel()
        assert model.rowCount() == 0
        assert model.columnCount() == 2
        assert model.headerData(0, Qt.Orientation.Horizontal) == "任务"
        assert model.headerData(1, Qt.Orientation.Horizontal) == "时间轴"

    def test_rows_and_display(self, qapp):
        model = TimelineTableModel()
        model.set_data(_sample_data())
        assert model.rowCount() == 2
        assert model.data(model.index(0, 0)) == "重构认证"
        assert model.data(model.index(1, 0)) == "补测试"
        assert model.data(model.index(0, 1)) is None  # 第 1 列由委托绘制

    def test_row_at_and_tooltip(self, qapp):
        model = TimelineTableModel()
        model.set_data(_sample_data())
        row = model.row_at(0)
        assert row is not None and row.task_id == "a"
        assert model.row_at(99) is None
        tip = model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole)
        assert "进行中" in tip and "60%" in tip

    def test_child_index_has_no_children(self, qapp):
        model = TimelineTableModel()
        model.set_data(_sample_data())
        assert model.rowCount(model.index(0, 0)) == 0
        assert model.columnCount(model.index(0, 0)) == 0


# ---------------------------------------------------------------------------
# 视图（离线渲染）
# ---------------------------------------------------------------------------


class TestTimelineTableView:
    def test_set_timeline_populates_rows(self, qtbot):
        view = TimelineTableView()
        qtbot.addWidget(view)
        view.resize(800, 200)
        view.set_timeline(_sample_data())
        assert view.table_model.rowCount() == 2
        assert view.timeline is not None

    def test_render_is_not_blank(self, qtbot):
        """渲染进 QPixmap 后颜色数 > 3，说明网格/色条/表头确有绘制。"""
        view = TimelineTableView()
        qtbot.addWidget(view)
        view.resize(800, 200)
        view.set_timeline(_sample_data())

        pixmap = QPixmap(view.size())
        pixmap.fill()
        view.render(pixmap)
        image = pixmap.toImage()

        colors = set()
        for y in range(0, image.height(), 3):
            for x in range(0, image.width(), 3):
                colors.add(image.pixel(x, y))
        assert len(colors) > 3

    def test_click_emits_selected(self, qtbot):
        view = TimelineTableView()
        qtbot.addWidget(view)
        view.resize(800, 200)
        view.set_timeline(_sample_data())

        seen: list[str] = []
        view.task_selected.connect(seen.append)
        view.selectRow(1)
        view.clicked.emit(view.table_model.index(1, 0))
        assert seen == ["b"]
        assert view.selected_task_id() == "b"

    def test_double_click_emits_activated(self, qtbot):
        view = TimelineTableView()
        qtbot.addWidget(view)
        view.resize(800, 200)
        view.set_timeline(_sample_data())

        seen: list[str] = []
        view.task_activated.connect(seen.append)
        view.doubleClicked.emit(view.table_model.index(0, 0))
        assert seen == ["a"]

    def test_empty_timeline_render_safe(self, qtbot):
        view = TimelineTableView()
        qtbot.addWidget(view)
        view.resize(400, 120)
        view.set_timeline(None)
        pixmap = QPixmap(view.size())
        pixmap.fill()
        view.render(pixmap)  # 不应抛异常
        assert view.table_model.rowCount() == 0


# ---------------------------------------------------------------------------
# 控制器（真库 + 总线去抖）
# ---------------------------------------------------------------------------


@pytest.fixture
def ctrl(tmp_path, qapp, qtbot):
    repo = TaskRepository(str(tmp_path / "timeline.db"))
    repo.open()
    svc = TaskService(repo, signal_bus=get_signal_bus())
    view = TimelineTableView()
    qtbot.addWidget(view)
    view.resize(800, 200)
    selection = SelectionContext()
    controller = TimelineController(svc, view, selection=selection)
    yield controller, svc, repo, view, selection
    # 清掉待触发的去抖定时器，避免仓库关闭后仍被回调
    controller._refresh_interval_ms = 0
    controller.flush_pending_refresh()
    view.deleteLater()
    repo.close()


class TestTimelineController:
    def test_refresh_builds_rows(self, ctrl):
        controller, svc, repo, view, selection = ctrl
        svc.create_task("- [ ] 时间轴任务 #t")
        data = controller.refresh()
        assert data.row_count >= 1
        assert view.table_model.rowCount() == data.row_count

    def test_selection_written_to_context(self, ctrl):
        controller, svc, repo, view, selection = ctrl
        task = svc.create_task("- [ ] 选中任务 #s")
        controller.refresh()

        seen: list[str] = []
        controller.task_selected.connect(seen.append)
        view.selectRow(0)
        view.clicked.emit(view.table_model.index(0, 0))

        assert seen == [task.id]
        assert selection.selected_task_id == task.id

    def test_range_and_sort_validation(self, ctrl):
        controller, svc, repo, view, selection = ctrl
        controller.set_range("month")
        assert controller.range_key == "month"
        with pytest.raises(ValueError):
            controller.set_range("decade")

        controller.set_sort("urgency")
        assert controller.sort_key == "urgency"
        with pytest.raises(ValueError):
            controller.set_sort("nonsense")

    def test_bus_refresh_is_debounced(self, ctrl):
        controller, svc, repo, view, selection = ctrl
        task = svc.create_task("- [ ] 去抖 #d")
        assert controller._refresh_interval_ms > 0

        controller.refresh()
        assert view.table_model.rowCount() == 1

        repo.delete(task.id)  # 绕过 service，不发信号
        get_signal_bus().task_updated.emit(task)
        # 去抖窗口内模型未刷新
        assert view.table_model.rowCount() == 1
        controller.flush_pending_refresh()
        assert view.table_model.rowCount() == 0

    def test_search_filter(self, ctrl):
        controller, svc, repo, view, selection = ctrl
        svc.create_task("- [ ] 甲任务 #alpha")
        svc.create_task("- [ ] 乙任务 #beta")
        controller.refresh()
        assert view.table_model.rowCount() == 2

        controller.set_filters(search_text="甲")
        assert view.table_model.rowCount() == 1
        assert view.table_model.row_at(0).title == "甲任务"
