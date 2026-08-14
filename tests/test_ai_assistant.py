"""AI 助手启动器测试 — 单 provider 检测逻辑."""

from __future__ import annotations

import pytest

from src.config import AppConfig
from src.services import ai_assistant
from src.services.ai_assistant import detect_provider


@pytest.fixture
def cfg(tmp_path) -> AppConfig:
    return AppConfig(tmp_path)


def test_explicit_provider_installed(cfg, monkeypatch):
    cfg.set("ai_assistant", "provider", value="codex")
    monkeypatch.setattr(ai_assistant, "_resolve_cmd", lambda cmd: cmd if cmd == "codex" else None)
    assert detect_provider(cfg) == "codex"


def test_explicit_provider_missing_unavailable(cfg, monkeypatch):
    """配置了 provider 但未安装 → 不可用，不回退到另一个."""
    cfg.set("ai_assistant", "provider", value="codex")
    monkeypatch.setattr(ai_assistant, "_resolve_cmd", lambda cmd: None)
    assert detect_provider(cfg) is None


def test_auto_detect_claude_priority(cfg, monkeypatch):
    monkeypatch.setattr(ai_assistant, "_resolve_cmd", lambda cmd: cmd)
    assert detect_provider(cfg) == "claude"


def test_auto_detect_fallback_codex(cfg, monkeypatch):
    monkeypatch.setattr(ai_assistant, "_resolve_cmd", lambda cmd: cmd if cmd == "codex" else None)
    assert detect_provider(cfg) == "codex"


def test_auto_detect_unavailable(cfg, monkeypatch):
    monkeypatch.setattr(ai_assistant, "_resolve_cmd", lambda cmd: None)
    assert detect_provider(cfg) is None


def test_workspace_dir_created(cfg):
    ws = ai_assistant._workspace_dir(cfg)
    assert ws.exists() and ws.name == "ai_workspace"
