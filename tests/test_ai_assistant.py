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


def test_project_slug():
    assert ai_assistant._project_slug(
        "D:\\MyCCProject\\Test\\resources\\ai_workspace"
    ) == "D--MyCCProject-Test-resources-ai-workspace"


def test_session_usage_percent(tmp_path, monkeypatch):
    """从会话 jsonl 的 usage 字段估算上下文用量百分比."""
    monkeypatch.setattr(ai_assistant, "_sessions_dir",
                        lambda provider, workspace: tmp_path)
    session = tmp_path / "s1.jsonl"
    session.write_text(
        "\n".join([
            '{"type": "user", "message": {}}',
            '{"type": "assistant", "message": {"usage": {"input_tokens": 100000,'
            ' "cache_read_input_tokens": 40000, "cache_creation_input_tokens": 0,'
            ' "output_tokens": 1000}}}',
            '{"type": "assistant", "message": {"usage": {"input_tokens": 160000,'
            ' "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,'
            ' "output_tokens": 2000}}}',
        ]),
        encoding="utf-8",
    )
    pct = ai_assistant.session_usage_percent("claude", str(tmp_path), "s1")
    assert pct == pytest.approx(162000 / 200000 * 100)  # 取最后一个 usage
    empty = tmp_path / "empty.jsonl"
    empty.write_text('{"type": "user", "message": {}}', encoding="utf-8")
    assert ai_assistant.session_usage_percent("claude", str(tmp_path), "empty") is None


def test_latest_and_capture_session(tmp_path, monkeypatch):
    import time as _time

    monkeypatch.setattr(ai_assistant, "_sessions_dir",
                        lambda provider, workspace: tmp_path)
    (tmp_path / "old.jsonl").write_text("{}", encoding="utf-8")
    _time.sleep(0.05)
    old_mtime = (tmp_path / "old.jsonl").stat().st_mtime
    _time.sleep(0.05)
    (tmp_path / "new.jsonl").write_text("{}", encoding="utf-8")
    assert ai_assistant.latest_session_id("claude", str(tmp_path)) == "new"
    assert ai_assistant.capture_new_session("claude", str(tmp_path), old_mtime, timeout=2) == "new"
    assert ai_assistant.capture_new_session("claude", str(tmp_path),
                                            _time.time() + 10, timeout=0.5) is None


def test_resume_command():
    assert ai_assistant.resume_command("claude", "abc123") == "claude --resume abc123"
    assert ai_assistant.resume_command("codex", "abc123") == "codex resume abc123"
