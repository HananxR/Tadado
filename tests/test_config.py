"""AppConfig 测试 — 默认值隔离与实例独立性."""

from __future__ import annotations

from src.config import DEFAULT_CONFIG, AppConfig


def test_set_does_not_mutate_process_defaults(tmp_path):
    """set() 修改不得污染全局 DEFAULT_CONFIG（回归：嵌套 dict 共享引用）."""
    c1 = AppConfig(tmp_path)
    c1.set("ai_assistant", "provider", value="codex")
    assert c1.get("ai_assistant", "provider") == "codex"
    assert DEFAULT_CONFIG["ai_assistant"]["provider"] == ""

    c2 = AppConfig(tmp_path / "other")
    assert c2.get("ai_assistant", "provider") == ""


def test_instances_are_independent(tmp_path):
    """两个实例互不共享嵌套配置."""
    c1 = AppConfig(tmp_path / "a")
    c2 = AppConfig(tmp_path / "b")
    c1.set("display", "theme", value="dark")
    assert c2.theme == "light"
    assert c1.theme == "dark"
