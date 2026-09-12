"""Tests for 视图注册表 — 页面接入点与旧视图名别名。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from src.ui.views import VIEW_REGISTRY, ViewSpec, get_spec, register, resolve


def test_five_pages_registered():
    assert list(VIEW_REGISTRY.keys()) == [
        "overview",
        "tasks",
        "graph",
        "analysis",
        "manage",
    ]


def test_groups(qapp):
    assert [VIEW_REGISTRY[p].group for p in VIEW_REGISTRY] == [
        "工作",
        "工作",
        "洞察",
        "洞察",
        "管理",
    ]


def test_factory_returns_widget(qapp):
    # 占位页可直接实例化；真实工厂需 main_window 依赖（由 MainWindow 装配时验证）
    for pid in ("overview", "graph"):
        w = VIEW_REGISTRY[pid].factory(None, {})
        assert isinstance(w, QWidget), f"{pid} factory 未返回 QWidget"
    for pid in ("tasks", "analysis", "manage"):
        assert callable(VIEW_REGISTRY[pid].factory), f"{pid} factory 不可调用"


def test_alias_resolution():
    assert resolve("edit") == "tasks"
    assert resolve("dashboard") == "analysis"
    assert resolve("batch") == "manage"
    assert resolve("tasks") == "tasks"
    assert resolve("unknown") == "unknown"
    assert get_spec("edit") is VIEW_REGISTRY["tasks"]


def test_register_aliases(qapp):
    spec = ViewSpec(
        id="tmp_page",
        title="T",
        group="工作",
        icon="tasks",
        factory=lambda parent=None, **_deps: QWidget(parent),
        aliases=("tmp_alias",),
    )
    register(spec)
    try:
        assert get_spec("tmp_alias") is spec
    finally:
        del VIEW_REGISTRY["tmp_page"]
        VIEW_REGISTRY.pop("tmp_alias", None)
