"""Task graph service — 把任务、标签、分区与 ``[[链接]]`` 关系构建成可单测的图。

纯 Python 实现，不依赖任何 Qt / UI 组件，便于单元测试与复用。
节点/边排序确定，同一输入两次调用结果完全相等（force-directed 布局可复现）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.task import Task
from ..models.task_status import TaskStatus
from .md_parser import MarkdownTaskParser


@dataclass(frozen=True)
class GraphNode:
    """图中的节点（不可变，可直接比较/排序）。"""

    id: str  # "task:<uuid>" | "tag:<casefolded name>" | "part:<id>"
    kind: str  # "task" | "tag" | "partition"
    label: str
    status: str | None  # task: TaskStatus.value；tag/partition: None
    urgency: int  # task: urgency；tag/partition: -1
    degree: int  # 在最终边集合中的度数（无向统计）


@dataclass(frozen=True)
class GraphEdge:
    """图中的边。"""

    source: str
    target: str
    kind: str  # "tag" | "partition" | "link"


class TaskGraphService:
    """构建任务关系图（节点 + 边）。"""

    def __init__(self) -> None:
        self._parser = MarkdownTaskParser()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_graph(
        self,
        tasks: list[Task],
        partitions: list[dict] | None = None,
        *,
        include_tags: bool = True,
        include_partitions: bool = True,
        include_links: bool = True,
        hide_done: bool = False,
        only_related: bool = False,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """构建任务图。

        Args:
            tasks: 任务列表。
            partitions: 分区字典列表（每项含 ``"id"`` / ``"name"``），用于分区节点 label。
            include_tags: 是否包含标签节点与 task→tag 边。
            include_partitions: 是否包含分区节点与 task→partition 边。
            include_links: 是否包含 task→task 的 ``[[链接]]`` 边。
            hide_done: 隐藏已完成（DONE）任务及其相关边；度数为 0 的 tag/partition 一并剪除。
            only_related: 仅保留存在 link 边的任务，及其直接关联节点与这些任务之间的边。

        Returns:
            ``(nodes, edges)``；节点按 ``id`` 排序，边按 ``(source, target, kind)`` 排序。
        """
        partition_labels: dict[str, str] = {}
        for part in partitions or []:
            pid = part.get("id")
            if pid:
                partition_labels[pid] = part.get("name") or f"part:{pid}"

        task_meta: dict[str, tuple[str, str | None, int]] = {}
        for task in tasks:
            task_meta[self._task_id(task)] = (
                getattr(task, "title", "") or "",
                task.status.value,
                getattr(task, "urgency", 3),
            )

        tag_meta: dict[str, str] = {}  # id -> 首次出现原文 label
        part_meta: dict[str, str] = {}  # id -> label
        edges: set[tuple[str, str, str]] = set()

        if include_tags:
            for task in tasks:
                tid = self._task_id(task)
                for tag in getattr(task, "tags", []) or []:
                    key = self._tag_id(tag)
                    tag_meta.setdefault(key, tag)
                    edges.add((tid, key, "tag"))

        if include_partitions:
            for task in tasks:
                pid = getattr(task, "partition_id", None) or ""
                if not pid:
                    continue
                key = self._part_id(pid)
                part_meta.setdefault(key, partition_labels.get(pid, key))
                edges.add((self._task_id(task), key, "partition"))

        if include_links:
            lookup: dict[str, str] = {}
            for task in tasks:
                tid = self._task_id(task)
                for name in self._node_title_keys(task):
                    if name:
                        lookup.setdefault(name, tid)
            for task in tasks:
                tid = self._task_id(task)
                for link in self._task_links(task):
                    target = lookup.get(link)
                    if target and target != tid:  # 匹配不到 / 自环 → 不产生边
                        edges.add((tid, target, "link"))

        if hide_done:
            removed = {self._task_id(t) for t in tasks if t.status == TaskStatus.DONE}
            edges = {e for e in edges if e[0] not in removed and e[1] not in removed}
            for rid in removed:
                task_meta.pop(rid, None)

        if only_related:
            related: set[str] = set()
            for src, tgt, kind in edges:
                if kind == "link":
                    related.add(src)
                    related.add(tgt)
            removed = set(task_meta) - related
            edges = {e for e in edges if e[0] not in removed and e[1] not in removed}
            for rid in removed:
                task_meta.pop(rid, None)

        # 剪掉度数为 0 的 tag / partition 节点
        used: set[str] = set()
        for src, tgt, _kind in edges:
            used.add(src)
            used.add(tgt)
        for key in list(tag_meta):
            if key not in used:
                tag_meta.pop(key)
        for key in list(part_meta):
            if key not in used:
                part_meta.pop(key)

        degree: dict[str, int] = {}
        for src, tgt, _kind in edges:
            degree[src] = degree.get(src, 0) + 1
            degree[tgt] = degree.get(tgt, 0) + 1

        nodes: list[GraphNode] = []
        for nid, (label, status, urgency) in task_meta.items():
            nodes.append(GraphNode(nid, "task", label, status, urgency, degree.get(nid, 0)))
        for nid, label in tag_meta.items():
            nodes.append(GraphNode(nid, "tag", label, None, -1, degree.get(nid, 0)))
        for nid, label in part_meta.items():
            nodes.append(GraphNode(nid, "partition", label, None, -1, degree.get(nid, 0)))

        nodes.sort(key=lambda n: n.id)
        edge_objs = sorted(
            (GraphEdge(s, t, k) for s, t, k in edges),
            key=lambda e: (e.source, e.target, e.kind),
        )
        return nodes, edge_objs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _task_id(task: Task) -> str:
        return f"task:{task.id}"

    @staticmethod
    def _tag_id(name: str) -> str:
        """标签节点 id：大小写不敏感归一。"""
        return f"tag:{name.casefold()}"

    @staticmethod
    def _part_id(pid: str) -> str:
        return f"part:{pid}"

    @staticmethod
    def _node_title_keys(task: Task) -> list[str]:
        """用于链接匹配的标题键（title + 解析出的 clean_title）。"""
        keys = [getattr(task, "title", "") or ""]
        raw_md = getattr(task, "raw_md", "") or ""
        if raw_md:
            try:
                parsed = MarkdownTaskParser().parse(raw_md)
            except ValueError:
                parsed = None
            if parsed is not None and parsed.clean_title:
                keys.append(parsed.clean_title)
        return keys

    def _task_links(self, task: Task) -> list[str]:
        """任务的 ``[[链接]]`` 目标名：显式 ``links`` 优先，否则解析 ``raw_md``。"""
        links = getattr(task, "links", None)
        if links is not None:
            return list(links)
        raw_md = getattr(task, "raw_md", "") or ""
        if raw_md:
            try:
                return list(self._parser.parse(raw_md).links)
            except ValueError:
                pass
        return MarkdownTaskParser._extract_links(getattr(task, "title", "") or "")
