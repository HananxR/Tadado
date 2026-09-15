"""AppConfig 测试 — 默认值隔离与实例独立性."""

from __future__ import annotations

import json

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


def test_general_hotkey_and_pin_on_top_defaults(tmp_path):
    """新增默认键 hotkey / pin_on_top 应存在且取值正确（阶段 5）."""
    assert DEFAULT_CONFIG["general"]["hotkey"] == "Ctrl+Shift+Space"
    assert DEFAULT_CONFIG["general"]["pin_on_top"] is False

    c = AppConfig(tmp_path)
    assert c.get("general", "hotkey") == "Ctrl+Shift+Space"
    assert c.get("general", "pin_on_top") is False


def test_legacy_config_backfilled_by_deep_merge(tmp_path):
    """缺少新键的旧配置文件加载后应被自动补齐默认值."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    legacy = {"general": {"page_size": 50}}  # 旧配置没有 hotkey / pin_on_top
    (tmp_path / "config.json").write_text(json.dumps(legacy), encoding="utf-8")

    c = AppConfig(tmp_path)
    assert c.get("general", "hotkey") == "Ctrl+Shift+Space"
    assert c.get("general", "pin_on_top") is False
    assert c.get("general", "page_size") == 50  # 旧值保留
