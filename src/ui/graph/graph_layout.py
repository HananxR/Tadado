"""力导向布局（纯 Python / 无 Qt / 确定性）。

初始位置按圆环等距分布（不使用随机数），迭代过程完全由输入决定，
因此 ``variant`` 相同 ⇒ 布局完全相同 —— 满足「重新布局可复现」的测试要求。

复杂度 O(iterations × n²)，适用于任务图谱量级（n ≤ 数百）。
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]


def force_directed_layout(
    node_ids: Sequence[str],
    edges: Iterable[tuple[str, str]],
    width: float,
    height: float,
    *,
    iterations: int = 220,
    padding: float = 36.0,
    variant: int = 0,
    repulsion: float = 2600.0,
    attraction: float = 0.012,
    damping: float = 0.86,
) -> dict[str, Point]:
    """计算节点坐标（左上原点，坐标已夹在 padding 内）。

    Args:
        node_ids: 节点 id（顺序决定初始圆环角度）。
        edges: ``(source, target)`` 对（方向无关）。
        width / height: 画布尺寸。
        iterations: 迭代次数。
        padding: 边距（坐标夹取范围）。
        variant: 布局变体（相同输入 + 相同 variant ⇒ 相同结果）。
        repulsion / attraction / damping: 力模型参数。
    """
    count = len(node_ids)
    if count == 0:
        return {}
    if count == 1:
        return {node_ids[0]: (width / 2.0, height / 2.0)}

    cx, cy = width / 2.0, height / 2.0
    radius = max(20.0, min(width, height) / 2.0 - padding)
    pos: dict[str, list[float]] = {}
    for i, nid in enumerate(node_ids):
        angle = 2.0 * math.pi * i / count + variant * 0.37
        pos[nid] = [cx + math.cos(angle) * radius, cy + math.sin(angle) * radius]

    index = {nid: i for i, nid in enumerate(node_ids)}
    pairs: list[tuple[int, int]] = []
    for src, tgt in edges:
        if src in index and tgt in index and src != tgt:
            pairs.append((index[src], index[tgt]))

    displacements = [[0.0, 0.0] for _ in range(count)]
    for _ in range(max(0, iterations)):
        for d in displacements:
            d[0] = 0.0
            d[1] = 0.0

        # 斥力：所有节点对
        for i in range(count):
            xi, yi = pos[node_ids[i]]
            for j in range(i + 1, count):
                xj, yj = pos[node_ids[j]]
                dx, dy = xi - xj, yi - yj
                dist2 = dx * dx + dy * dy
                if dist2 < 1e-6:
                    dx, dy = (i - j) * 0.7 + 0.31, (j - i) * 0.7 + 0.17
                    dist2 = dx * dx + dy * dy
                dist = math.sqrt(dist2)
                force = repulsion / dist2
                ux, uy = dx / dist, dy / dist
                displacements[i][0] += ux * force
                displacements[i][1] += uy * force
                displacements[j][0] -= ux * force
                displacements[j][1] -= uy * force

        # 引力：沿边收缩
        for i, j in pairs:
            xi, yi = pos[node_ids[i]]
            xj, yj = pos[node_ids[j]]
            dx, dy = xj - xi, yj - yi
            displacements[i][0] += dx * attraction
            displacements[i][1] += dy * attraction
            displacements[j][0] -= dx * attraction
            displacements[j][1] -= dy * attraction

        for i, nid in enumerate(node_ids):
            p = pos[nid]
            p[0] += displacements[i][0] * damping
            p[1] += displacements[i][1] * damping

    lo_x, hi_x = padding, max(padding, width - padding)
    lo_y, hi_y = padding, max(padding, height - padding)
    return {
        nid: (
            min(hi_x, max(lo_x, pos[nid][0])),
            min(hi_y, max(lo_y, pos[nid][1])),
        )
        for nid in node_ids
    }


def neighbour_map(edges: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    """无向邻接表（用于 hover 高亮）。"""
    adj: dict[str, set[str]] = {}
    for src, tgt in edges:
        adj.setdefault(src, set()).add(tgt)
        adj.setdefault(tgt, set()).add(src)
    return adj


__all__ = ["Point", "force_directed_layout", "neighbour_map"]
