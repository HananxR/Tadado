"""MainWindow 无头冒烟测试 — 阶段 2 刷新管线/分页重构的端到端守门。

对应 TODO(阶段1收尾)「真机 GUI 冒烟」的无头替代：以 offscreen 平台真实
构建 MainWindow（含 NavShell / 任务页 / FilterCoordinator），验证
视图切换、分页移交与数据刷新仍然可用。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from src.config import AppConfig
from src.models.repository import TaskRepository
from src.services.task_service import TaskService
from src.ui.main_window import MainWindow
from src.utils import design_tokens
from src.utils.signal_bus import get_signal_bus


@pytest.fixture
def mw(tmp_path, qapp):
    """Build a real MainWindow on a temp config + DB (offscreen)."""
    config = AppConfig(tmp_path)
    config.set("general", "page_size", value=2)
    design_tokens.init_tokens(config)

    repo = TaskRepository(str(tmp_path / "tadado.db"))
    repo.open()
    svc = TaskService(repo, signal_bus=get_signal_bus())
    window = MainWindow(config, repo, task_service=svc)
    yield window, svc, repo, config
    # Destroy the window (and its FilterCoordinator) before closing the DB so
    # no bus subscriptions outlive the repository.
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    # TaskService 不是 QObject，Qt 不会自动断连 —— 必须显式解绑，
    # 否则后续用例发信号时旧实例仍会回调已关闭的 repository。
    svc.dispose()
    repo.close()


def _clear_tasks(svc, repo) -> None:
    for task in repo.get_all():
        repo.delete(task.id)


def test_window_builds_default_task_page(mw):
    window, svc, repo, config = mw
    assert window._current_page == "tasks"
    # 阶段 3：任务页 = 时间轴 + 工具行（旧列表 / 过滤栏 / FilterCoordinator 均已退役）
    assert window._timeline_ctl is not None
    assert window._timeline_view.table_model.rowCount() == 0


def test_task_page_is_the_visible_stack_page(mw):
    """启动后主区域必须显示任务页，而不是 overview 的空占位。"""
    window, svc, repo, config = mw
    assert window._stack.currentIndex() == window._page_index["tasks"]
    assert not window._stack.currentWidget().isHidden()


def test_created_task_reaches_timeline(mw):
    """Bus → TimelineController → 时间轴：新建任务后任务页出现该行。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id

    svc.create_task("- [ ] 冒烟任务 #smoke", partition_id=pid)
    window._timeline_ctl.refresh()

    model = window._timeline_view.table_model
    titles = [model.row_at(i).title for i in range(model.rowCount())]
    assert "冒烟任务" in titles


def test_timeline_shows_created_task(mw):
    """阶段 3 集成：任务页时间轴展示新建任务。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    svc.create_task("- [ ] 时间轴集成 #tl", partition_id=pid)

    window._timeline_ctl.refresh()
    model = window._timeline_view.table_model
    titles = [model.row_at(i).title for i in range(model.rowCount())]
    assert "时间轴集成" in titles


def test_timeline_selection_writes_context_and_editor(mw):
    """时间轴选中 → SelectionContext + 过渡期编辑器载入。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    task = svc.create_task("- [ ] 选中任务 #tl", partition_id=pid)
    window._timeline_ctl.refresh()

    window._timeline_view.task_selected.emit(task.id)

    assert window._selection.selected_task_id == task.id


def test_timeline_bus_refresh_is_debounced(mw):
    """阶段 7：总线驱动的刷新被去抖合并，flush 后才生效。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    tl = window._timeline_ctl
    assert tl._refresh_interval_ms > 0

    task = svc.create_task("- [ ] 去抖任务 #debounce", partition_id=pid)
    tl.refresh()
    assert window._timeline_view.table_model.rowCount() == 1

    # 绕过 service 直接删库（不触发信号），再手动发一条总线事件
    _clear_tasks(svc, repo)
    svc._bus.task_updated.emit(task)

    # 去抖窗口内尚未刷新
    assert window._timeline_view.table_model.rowCount() == 1
    tl.flush_pending_refresh()
    assert window._timeline_view.table_model.rowCount() == 0


def test_view_switching_round_trip(mw):
    """切换 图谱 / 分析 / 管理 / 任务 四页不应抛异常，且回到任务页。"""
    window, svc, repo, config = mw

    window._switch_view("graph")
    assert window._current_page == "graph"

    window._switch_view("analysis")
    assert window._current_page == "analysis"

    window._switch_view("manage")
    assert window._current_page == "manage"

    window._switch_view("edit")  # 旧名别名 → tasks
    assert window._current_page == "tasks"


def test_overview_page_integration(mw):
    """阶段 4 集成：总览页统计瓦片/焦点时间轴/近期活动/紧迫度分布可用。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    svc.create_task("- [ ] 总览任务 #ov", partition_id=pid)

    window._switch_view("overview")
    assert window._current_page == "overview"

    page = window._overview_page
    page.set_partition(pid)
    page.refresh()
    assert page._tile_due._value.text().isdigit()  # 瓦片已渲染数值
    assert page._timeline.table_model.rowCount() >= 0

    # 焦点时间轴预设切换
    page.set_range("month")
    assert page.range_key == "month"

    # 快速新建
    page._quick_input.setText("- [ ] 总览快建 #quick")
    page._on_quick_add()
    titles = [t.title for t in svc.get_all()]
    assert "总览快建" in titles

    # 瓦片点击 → 回到任务页
    window._switch_view("overview")
    page._tile_over.clicked.emit()
    assert window._current_page == "tasks"


def test_graph_page_integration(mw):
    """阶段 6 集成：图谱页出节点；双击任务节点回到任务页并载入编辑器。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    svc.create_task("- [ ] 图谱集成 [[目标]] #g", partition_id=pid)
    svc.create_task("- [ ] 目标 #g2", partition_id=pid)

    window._switch_view("graph")
    assert window._current_page == "graph"
    window._graph_ctl.refresh()

    task_nodes = [n for n in window._graph_view.nodes if n.kind == "task"]
    assert any("图谱集成" in n.label for n in task_nodes)
    assert any(e.kind == "link" for e in window._graph_view.edges)

    task_id = task_nodes[0].id.split(":", 1)[1]
    window._graph_view.task_activated.emit(task_id)
    assert window._current_page == "tasks"

    drawer = window._ensure_drawer()
    assert drawer.is_open is True
    assert drawer.current_task is not None
    assert drawer.current_task.id == task_id


def test_timeline_toolbar_search_filters_rows(mw):
    """工具行搜索 → TimelineController.set_filters → 时间轴只剩匹配行。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    svc.create_task("- [ ] 苹果 #toolbar", partition_id=pid)
    svc.create_task("- [ ] 香蕉 #toolbar", partition_id=pid)

    window._timeline_ctl.refresh()
    assert window._timeline_view.table_model.rowCount() == 2

    window._timeline_search.setText("苹果")

    model = window._timeline_view.table_model
    assert model.rowCount() == 1
    assert model.row_at(0).title == "苹果"


def test_timeline_toolbar_status_chip_filters_rows(mw):
    """状态 chips（互斥）→ 时间轴过滤；「全部」不过滤。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    svc.create_task("- [ ] 待办项 #chip", partition_id=pid)

    window._timeline_ctl.refresh()
    assert window._timeline_view.table_model.rowCount() == 1

    # 切到「已完成」→ 待办项被过滤掉
    window._timeline_status_chips["done"].setChecked(True)
    window._apply_timeline_filters()
    assert window._timeline_view.table_model.rowCount() == 0

    # 回到「全部」→ 恢复不过滤
    window._timeline_status_chips["all"].setChecked(True)
    window._apply_timeline_filters()
    assert window._timeline_view.table_model.rowCount() == 1


def test_timeline_toolbar_sort_switch(mw):
    """排序下拉 → TimelineController.set_sort。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    svc.create_task("- [ ] 排序项 #sort", partition_id=pid)
    window._timeline_ctl.refresh()

    idx = window._timeline_sort_combo.findData("urgency")
    assert idx >= 0
    window._timeline_sort_combo.setCurrentIndex(idx)

    assert window._timeline_ctl.sort_key == "urgency"


def test_timeline_defers_refresh_while_hidden(mw):
    """阶段 7：任务页不在前台时，总线刷新只标记 dirty，切回时回放。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    window._timeline_ctl.refresh()
    assert window._timeline_view.table_model.rowCount() == 0

    # 切到分析页 → 任务页时间轴离屏
    window._switch_view("analysis")
    assert window._timeline_ctl.is_visible is False

    svc.create_task("- [ ] 延迟刷新 #dirty", partition_id=pid)
    window._timeline_ctl.flush_pending_refresh()  # 不可见 → 只标记 dirty

    assert window._timeline_ctl.is_dirty is True
    assert window._timeline_view.table_model.rowCount() == 0

    # 切回任务页 → 回放延后的刷新
    window._switch_view("tasks")
    assert window._timeline_ctl.is_dirty is False
    assert window._timeline_view.table_model.rowCount() == 1


def test_timeline_includes_completed_tasks(mw):
    """时间轴包含已完成任务。

    分区 ``archive_days=0`` 时「完成即归档」，若时间轴默认排除归档任务，
    任务一勾选完成就会从视野里消失。这里锁定「已完成仍显示」这一行为。
    """
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id

    svc.create_task("- [ ] DONE <2026-09-14> 已完成样例 #done", partition_id=pid)
    window._timeline_ctl.refresh()

    model = window._timeline_view.table_model
    rows = [(model.row_at(i).title, model.row_at(i).status) for i in range(model.rowCount())]
    assert ("已完成样例", "DONE") in rows


def test_status_chips_include_archived_done(mw):
    """chips 计数与时间轴同口径：已完成（已归档）也要计入。"""
    window, svc, repo, config = mw
    _clear_tasks(svc, repo)
    pid = window._partition_ctrl.active_id
    svc.create_task("- [ ] TODO <2026-09-16> 待办样例 #a", partition_id=pid)
    svc.create_task("- [ ] DONE <2026-09-14> 完成样例 #b", partition_id=pid)

    window._refresh_status_chip_counts()

    chips = window._timeline_status_chips
    assert chips["done"].text() == "已完成 1"
    assert chips["todo"].text() == "待办 1"
    assert chips["all"].text() == "全部 2"
