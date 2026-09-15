"""任务图谱测试 —— 布局 / 画布 / 控制器（阶段 6）。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap

from src.models.repository import TaskRepository
from src.services.task_graph import GraphEdge, GraphNode, TaskGraphService
from src.services.task_service import TaskService
from src.ui.graph import GraphController, TaskGraphView, force_directed_layout
from src.ui.graph.graph_layout import neighbour_map
from src.utils.signal_bus import get_signal_bus


def _make_nodes(*specs) -> list[GraphNode]:
    return [
        GraphNode(id=nid, kind=kind, label=label, status=status, urgency=u, degree=0)
        for nid, kind, label, status, u in specs
    ]


# ---------------------------------------------------------------------------
# 布局（纯函数）
# ---------------------------------------------------------------------------


class TestForceDirectedLayout:
    NODES = ["task:a", "task:b", "tag:x", "part:p1"]
    EDGES = [("task:a", "tag:x"), ("task:a", "part:p1"), ("task:a", "task:b")]

    def test_deterministic_same_variant(self):
        first = force_directed_layout(self.NODES, self.EDGES, 800, 600, variant=0)
        second = force_directed_layout(self.NODES, self.EDGES, 800, 600, variant=0)
        assert first == second

    def test_variant_changes_layout(self):
        base = force_directed_layout(self.NODES, self.EDGES, 800, 600, variant=0)
        other = force_directed_layout(self.NODES, self.EDGES, 800, 600, variant=1)
        assert base != other

    def test_positions_inside_padding(self):
        positions = force_directed_layout(self.NODES, self.EDGES, 800, 600, padding=30)
        for x, y in positions.values():
            assert 30 <= x <= 770
            assert 30 <= y <= 570

    def test_empty_and_single(self):
        assert force_directed_layout([], [], 400, 300) == {}
        assert force_directed_layout(["only"], [], 400, 300) == {"only": (200.0, 150.0)}

    def test_edges_to_unknown_nodes_ignored(self):
        positions = force_directed_layout(["a"], [("a", "ghost")], 200, 200)
        assert set(positions) == {"a"}

    def test_neighbour_map_is_undirected(self):
        adj = neighbour_map([("a", "b"), ("b", "c")])
        assert adj["a"] == {"b"}
        assert adj["b"] == {"a", "c"}
        assert adj["c"] == {"b"}


# ---------------------------------------------------------------------------
# 画布
# ---------------------------------------------------------------------------


def _sample_graph():
    nodes = _make_nodes(
        ("task:a", "task", "重构认证", "DOING", 1),
        ("task:b", "task", "补测试", "TODO", 3),
        ("tag:x", "tag", "后端", None, -1),
        ("part:p1", "partition", "工作", None, -1),
    )
    edges = [
        GraphEdge("task:a", "tag:x", "tag"),
        GraphEdge("task:a", "part:p1", "partition"),
        GraphEdge("task:a", "task:b", "link"),
    ]
    return nodes, edges


class TestTaskGraphView:
    def test_set_graph_positions_all_nodes(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(600, 400)
        nodes, edges = _sample_graph()
        view.set_graph(nodes, edges)
        assert set(view.positions) == {n.id for n in nodes}
        assert len(view.edges) == 3

    def test_render_is_not_blank(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(600, 400)
        view.set_graph(*_sample_graph())
        pixmap = QPixmap(view.size())
        pixmap.fill()
        view.render(pixmap)
        image = pixmap.toImage()
        colors = {
            image.pixel(x, y)
            for y in range(0, image.height(), 4)
            for x in range(0, image.width(), 4)
        }
        assert len(colors) > 3

    def test_empty_graph_render_is_safe(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(320, 240)
        view.set_graph([], [])
        pixmap = QPixmap(view.size())
        pixmap.fill()
        view.render(pixmap)
        assert view.positions == {}

    def test_node_at_hits_node(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(600, 400)
        view.set_graph(*_sample_graph())
        x, y = view.positions["task:a"]
        widget_point = view._to_widget(x, y)
        assert view.node_at(widget_point.x(), widget_point.y()) == "task:a"
        assert view.node_at(1.0, 1.0) == ""

    def test_hover_emits_and_tracks(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(600, 400)
        view.set_graph(*_sample_graph())

        seen: list[str] = []
        view.node_hovered.connect(seen.append)
        x, y = view.positions["tag:x"]
        point = view._to_widget(x, y)
        event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(point),
            QPointF(point),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseMoveEvent(event)
        assert view.hovered_node_id == "tag:x"
        assert seen == ["tag:x"]

    def test_double_click_emits_task_only(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(600, 400)
        view.set_graph(*_sample_graph())

        seen: list[str] = []
        view.task_activated.connect(seen.append)

        x, y = view.positions["task:b"]
        point = view._to_widget(x, y)
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonDblClick,
            QPointF(point),
            QPointF(point),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseDoubleClickEvent(event)
        assert seen == ["b"]

        # 标签节点双击不触发
        tx, ty = view.positions["tag:x"]
        tag_point = view._to_widget(tx, ty)
        view.mouseDoubleClickEvent(
            QMouseEvent(
                QMouseEvent.Type.MouseButtonDblClick,
                QPointF(tag_point),
                QPointF(tag_point),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        assert seen == ["b"]

    def test_zoom_clamped(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(600, 400)
        view.set_graph(*_sample_graph())
        for _ in range(40):
            view.zoom_in()
        assert view.scale_factor <= 3.0
        for _ in range(80):
            view.zoom_out()
        assert view.scale_factor >= 0.3
        view.reset_zoom()
        assert view.scale_factor == 1.0

    def test_relayout_changes_positions(self, qtbot):
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(600, 400)
        view.set_graph(*_sample_graph())
        before = view.positions
        view.relayout()
        assert view.positions != before


# ---------------------------------------------------------------------------
# 控制器
# ---------------------------------------------------------------------------


@pytest.fixture
def gc(tmp_path, qapp, qtbot):
    repo = TaskRepository(str(tmp_path / "graph.db"))
    repo.open()
    svc = TaskService(repo, signal_bus=get_signal_bus())
    view = TaskGraphView()
    qtbot.addWidget(view)
    view.resize(600, 400)
    controller = GraphController(svc, view)
    yield controller, svc, repo, view
    controller._refresh_interval_ms = 0
    controller.flush_pending_refresh()
    view.deleteLater()
    repo.close()


class TestGraphController:
    def test_refresh_builds_nodes_for_tasks(self, gc):
        controller, svc, repo, view = gc
        svc.create_task("- [ ] 图谱任务 [[目标]] #后端")
        svc.create_task("- [ ] 目标 #其他")
        nodes, edges = controller.refresh()
        assert any(n.kind == "task" for n in nodes)
        assert any(n.kind == "tag" for n in nodes)
        assert any(e.kind == "link" for e in edges)
        assert len(view.nodes) == len(nodes)

    def test_filter_validation(self, gc):
        controller, svc, repo, view = gc
        controller.set_filter("doing")
        assert controller.filter_key == "doing"
        with pytest.raises(ValueError):
            controller.set_filter("nope")

    def test_only_related_filter(self, gc):
        controller, svc, repo, view = gc
        svc.create_task("- [ ] 关联源 [[目标]] #a")
        svc.create_task("- [ ] 目标 #b")
        svc.create_task("- [ ] 孤立任务 #c")

        controller.set_only_related(True)
        assert all(n.kind != "task" or "孤立" not in n.label for n in view.nodes)

    def test_hide_done_filter(self, gc):
        controller, svc, repo, view = gc
        svc.create_task("- [x] DONE 已完成 #d")
        svc.create_task("- [ ] 未完成 #u")
        controller.set_hide_done(True)
        labels = [n.label for n in view.nodes if n.kind == "task"]
        assert "已完成" not in labels
        assert "未完成" in labels

    def test_task_activated_forwarded(self, gc):
        controller, svc, repo, view = gc
        seen: list[str] = []
        controller.task_activated.connect(seen.append)
        view.task_activated.emit("abc")
        assert seen == ["abc"]

    def test_bus_refresh_is_debounced(self, gc):
        controller, svc, repo, view = gc
        task = svc.create_task("- [ ] 去抖图 #g")
        assert controller._refresh_interval_ms > 0
        controller.refresh()
        assert any(n.label == "去抖图" for n in view.nodes)

        repo.delete(task.id)
        get_signal_bus().task_updated.emit(task)
        assert any(n.label == "去抖图" for n in view.nodes)  # 去抖窗口内未刷新
        controller.flush_pending_refresh()
        assert not any(n.label == "去抖图" for n in view.nodes)

    def test_relayout_delegates(self, gc):
        controller, svc, repo, view = gc
        svc.create_task("- [ ] 布局 #l")
        controller.refresh()
        before = view.positions
        controller.relayout()
        assert view.positions != before


# ---------------------------------------------------------------------------
# TaskGraphService 与画布的数据契约
# ---------------------------------------------------------------------------


def test_service_output_consumed_by_view(qapp, qtbot, tmp_path):
    """真实 service 输出可直接喂给画布。"""
    repo = TaskRepository(str(tmp_path / "g2.db"))
    repo.open()
    try:
        svc = TaskService(repo, signal_bus=get_signal_bus())
        svc.create_task("- [ ] A [[B]] #t")
        svc.create_task("- [ ] B #t")
        nodes, edges = TaskGraphService().build_graph(svc.get_all(), svc.get_all_partitions())
        view = TaskGraphView()
        qtbot.addWidget(view)
        view.resize(500, 320)
        view.set_graph(nodes, edges)
        assert len(view.nodes) == len(nodes)
        assert len(view.positions) == len(nodes)
    finally:
        repo.close()
