"""Tests for TaskGraphService — 纯 Python 图谱构建（阶段 6 数据层）。"""

from __future__ import annotations

from src.models.task import Task
from src.models.task_status import TaskStatus
from src.services.task_graph import GraphEdge, TaskGraphService


def make_task(
    task_id: str,
    title: str,
    *,
    tags: list[str] | None = None,
    status: TaskStatus = TaskStatus.TODO,
    urgency: int = 3,
    partition_id: str | None = None,
    raw_md: str | None = None,
) -> Task:
    """构造测试用 Task；raw_md 默认由 title 生成，可显式覆盖以承载 [[链接]]。"""
    return Task(
        id=task_id,
        raw_md=raw_md if raw_md is not None else f"- [ ] {title}",
        title=title,
        status=status,
        tags=list(tags or []),
        urgency=urgency,
        partition_id=partition_id,
    )


class TestNodeAndEdgeCounts:
    def test_basic_counts(self) -> None:
        tasks = [
            make_task("a", "任务A", tags=["后端"], partition_id="p1"),
            make_task("b", "任务B", tags=["前端"]),
        ]
        nodes, edges = TaskGraphService().build_graph(
            tasks, [{"id": "p1", "name": "工作"}]
        )
        assert {n.id for n in nodes} == {
            "task:a", "task:b", "tag:后端", "tag:前端", "part:p1",
        }
        assert len(nodes) == 5
        assert len(edges) == 3

        deg = {n.id: n.degree for n in nodes}
        assert deg["task:a"] == 2  # tag:后端 + part:p1
        assert deg["task:b"] == 1
        assert deg["tag:后端"] == 1
        assert deg["tag:前端"] == 1
        assert deg["part:p1"] == 1

    def test_task_node_metadata(self) -> None:
        nodes, _ = TaskGraphService().build_graph(
            [make_task("a", "A", status=TaskStatus.DOING, urgency=1)]
        )
        assert len(nodes) == 1
        node = nodes[0]
        assert node.kind == "task"
        assert node.status == "DOING"
        assert node.urgency == 1
        assert node.degree == 0

    def test_include_flags_disable_nodes(self) -> None:
        tasks = [make_task("a", "A", tags=["t"], partition_id="p1")]
        nodes, edges = TaskGraphService().build_graph(
            tasks,
            [{"id": "p1", "name": "P"}],
            include_tags=False,
            include_partitions=False,
        )
        assert {n.id for n in nodes} == {"task:a"}
        assert edges == []


class TestTagCaseInsensitive:
    def test_merge_different_case(self) -> None:
        tasks = [
            make_task("a", "A", tags=["Backend"]),
            make_task("b", "B", tags=["backend"]),
        ]
        nodes, edges = TaskGraphService().build_graph(tasks)
        tag_nodes = [n for n in nodes if n.kind == "tag"]
        assert len(tag_nodes) == 1
        assert tag_nodes[0].id == "tag:backend"
        assert tag_nodes[0].label == "Backend"  # label 取首次出现原文
        assert len(edges) == 2


class TestLinkEdges:
    def test_link_matched(self) -> None:
        tasks = [
            make_task("a", "重构", raw_md="- [ ] 重构 [[认证模块]]"),
            make_task("b", "认证模块"),
        ]
        _, edges = TaskGraphService().build_graph(tasks, include_tags=False)
        assert [e for e in edges if e.kind == "link"] == [
            GraphEdge("task:a", "task:b", "link")
        ]

    def test_link_unmatched_produces_nothing(self) -> None:
        tasks = [make_task("a", "重构", raw_md="- [ ] 重构 [[不存在的东西]]")]
        nodes, edges = TaskGraphService().build_graph(tasks, include_tags=False)
        assert edges == []
        assert {n.id for n in nodes} == {"task:a"}

    def test_link_self_reference_ignored(self) -> None:
        tasks = [make_task("a", "重构", raw_md="- [ ] 重构 [[重构]]")]
        _, edges = TaskGraphService().build_graph(tasks, include_tags=False)
        assert edges == []

    def test_link_disabled(self) -> None:
        tasks = [
            make_task("a", "重构", raw_md="- [ ] 重构 [[认证模块]]"),
            make_task("b", "认证模块"),
        ]
        _, edges = TaskGraphService().build_graph(
            tasks, include_tags=False, include_links=False
        )
        assert edges == []


class TestHideDone:
    def test_hide_done_removes_node_and_prunes_tag(self) -> None:
        tasks = [
            make_task("a", "A", tags=["x"]),
            make_task("b", "B", tags=["y"], status=TaskStatus.DONE),
        ]
        nodes, edges = TaskGraphService().build_graph(tasks, hide_done=True)
        ids = {n.id for n in nodes}
        assert "task:b" not in ids
        assert "tag:y" not in ids  # 度数归零被剪
        assert "task:a" in ids and "tag:x" in ids
        assert len(edges) == 1

    def test_hide_done_keeps_shared_tag(self) -> None:
        tasks = [
            make_task("a", "A", tags=["shared"]),
            make_task("b", "B", tags=["shared"], status=TaskStatus.DONE),
        ]
        nodes, edges = TaskGraphService().build_graph(tasks, hide_done=True)
        assert "tag:shared" in {n.id for n in nodes}
        assert len(edges) == 1


class TestOnlyRelated:
    def test_only_related(self) -> None:
        tasks = [
            make_task(
                "a", "重构", tags=["后端"], raw_md="- [ ] 重构 [[认证模块]] #后端"
            ),
            make_task("b", "认证模块", tags=["认证"]),
            make_task("c", "无关任务", tags=["杂项"]),
        ]
        nodes, edges = TaskGraphService().build_graph(tasks, only_related=True)
        ids = {n.id for n in nodes}
        assert ids == {"task:a", "task:b", "tag:后端", "tag:认证"}
        assert "task:c" not in ids
        assert "tag:杂项" not in ids
        assert len(edges) == 3

    def test_only_related_without_links_is_empty(self) -> None:
        tasks = [make_task("a", "A", tags=["x"])]
        nodes, edges = TaskGraphService().build_graph(tasks, only_related=True)
        assert nodes == []
        assert edges == []


class TestDeterminism:
    def test_two_calls_equal(self) -> None:
        tasks = [
            make_task(
                "a", "重构", tags=["后端"], partition_id="p1",
                raw_md="- [ ] 重构 [[认证模块]] #后端",
            ),
            make_task("b", "认证模块", tags=["认证"]),
            make_task("c", "其他", tags=["x", "y"], partition_id="p2"),
        ]
        partitions = [{"id": "p1", "name": "工作"}, {"id": "p2", "name": "个人"}]
        svc = TaskGraphService()
        assert svc.build_graph(tasks, partitions) == svc.build_graph(tasks, partitions)

    def test_node_and_edge_order_is_sorted(self) -> None:
        tasks = [make_task("b", "B", tags=["z"]), make_task("a", "A", tags=["Y"])]
        nodes, edges = TaskGraphService().build_graph(tasks)
        assert [n.id for n in nodes] == sorted(n.id for n in nodes)
        assert list(edges) == sorted(edges, key=lambda e: (e.source, e.target, e.kind))


class TestPartitionLabels:
    def test_named_partition(self) -> None:
        nodes, _ = TaskGraphService().build_graph(
            [make_task("a", "A", partition_id="p1")],
            [{"id": "p1", "name": "工作"}],
        )
        part = next(n for n in nodes if n.kind == "partition")
        assert part.id == "part:p1"
        assert part.label == "工作"
        assert part.status is None and part.urgency == -1

    def test_missing_partition_name_fallback(self) -> None:
        nodes, _ = TaskGraphService().build_graph(
            [make_task("a", "A", partition_id="p2")], []
        )
        part = next(n for n in nodes if n.kind == "partition")
        assert part.id == "part:p2"
        assert part.label == "part:p2"
