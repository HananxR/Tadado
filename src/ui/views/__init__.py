"""视图注册表 — 页面模块的唯一接入点。

新增页面 = 在此 ``register()`` 一个 ViewSpec，NavShell 自动渲染入口。
工厂约定：``factory(parent, deps) -> QWidget``，``deps`` 为共享依赖 dict
（task_service / config / repository / partition_ctrl / batch_ctrl /
filter_coordinator / selection ...）。

旧视图名经 VIEW_ALIASES 映射到新页面 id（edit → tasks 等），
兼容既有 ``_switch_view("edit")`` 调用点，待其全部迁移后移除。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ViewSpec:
    id: str
    title: str
    group: str  # 工作 | 洞察 | 管理
    icon: str  # ICON_DRAW_FUNCS 图标名
    factory: Callable[..., QWidget]
    description: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


# 旧视图名 → 新页面 id
VIEW_ALIASES = {"edit": "tasks", "dashboard": "analysis", "batch": "manage"}


VIEW_REGISTRY: dict[str, ViewSpec] = {}


def register(spec: ViewSpec) -> None:
    VIEW_REGISTRY[spec.id] = spec
    for alias in spec.aliases:
        VIEW_REGISTRY.setdefault(alias, spec)


def resolve(view_id: str) -> str:
    """旧视图名 → 新页面 id；未知 id 原样返回。"""
    return VIEW_ALIASES.get(view_id, view_id)


def get_spec(view_id: str) -> ViewSpec | None:
    return VIEW_REGISTRY.get(resolve(view_id))


def _placeholder_factory(title: str) -> Callable[..., QWidget]:
    """占位页工厂 — 真实页面落地后逐个替换（Phase 3/4/6）。"""
    from .placeholder_view import PlaceholderView

    def build(parent=None, deps=None):
        return PlaceholderView(title, parent=parent)

    return build


# ── 注册 5 个页面（侧边栏顺序 = 注册顺序） ──

register(
    ViewSpec(
        id="overview",
        title="总览",
        group="工作",
        icon="overview",
        factory=_placeholder_factory("总览"),
        description="今日焦点与总览统计（开发中）",
    )
)
register(
    ViewSpec(
        id="tasks",
        title="任务",
        group="工作",
        icon="tasks",
        factory=_placeholder_factory("任务"),
        description="任务浏览与编辑",
    )
)
register(
    ViewSpec(
        id="graph",
        title="任务图谱",
        group="洞察",
        icon="graph",
        factory=_placeholder_factory("任务图谱"),
        description="任务关系网络（开发中）",
    )
)
register(
    ViewSpec(
        id="analysis",
        title="活动分析",
        group="洞察",
        icon="heatmap",
        factory=_placeholder_factory("活动分析"),
        description="热力图与活动报告",
    )
)
register(
    ViewSpec(
        id="manage",
        title="任务管理",
        group="管理",
        icon="task_manage",
        factory=_placeholder_factory("任务管理"),
        description="批量审视与处置",
    )
)
