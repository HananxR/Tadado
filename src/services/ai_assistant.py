"""AI 助手启动器 — 从托盘启动专属 Claude Code / Codex 会话。

单 provider 架构：配置显式指定 claude/codex 之一；未配置时自动检测
（claude 优先）。两者都未安装 → AI 助手不可用。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

_log = logging.getLogger("runlog")

_WORKSPACE_DIR = "ai_workspace"
_DEFAULT_PROMPT = "/tadado 你好，我正在使用 Tadado AI 助手，请等待我的指令"

# Windows 常见安装位置（PATH 之外的兜底）
_KNOWN_PATHS: dict[str, tuple[str, ...]] = {
    "claude": (
        r"%USERPROFILE%\.local\bin\claude.exe",
        r"%LOCALAPPDATA%\Programs\claude\claude.exe",
        r"%APPDATA%\npm\claude.cmd",
    ),
    "codex": (
        r"%USERPROFILE%\.local\bin\codex.exe",
        r"%APPDATA%\npm\codex.cmd",
    ),
}


def _resolve_cmd(cmd: str) -> str | None:
    """Return the executable path for ``cmd`` or None when not installed."""
    found = shutil.which(cmd)
    if found:
        return found
    for pattern in _KNOWN_PATHS.get(cmd, ()):
        path = Path(os.path.expandvars(pattern))
        if path.exists():
            return str(path)
    return None


def detect_provider(config) -> str | None:
    """Resolve the single provider: explicit config wins, then auto-detect.

    Returns "claude" / "codex" / None (unavailable).
    """
    provider = (config.get("ai_assistant", "provider") or "").strip().lower()
    if provider in ("claude", "codex"):
        cmd = config.get("ai_assistant", f"{provider}_cmd") or provider
        if _resolve_cmd(cmd):
            return provider
        return None  # 用户指定了 provider 但未安装 → 不可用，不回退
    for candidate in ("claude", "codex"):  # 自动检测：claude 优先
        cmd = config.get("ai_assistant", f"{candidate}_cmd") or candidate
        if _resolve_cmd(cmd):
            return candidate
    return None


def _workspace_dir(config) -> Path:
    """Dedicated workspace so project-level skills are only tadado's."""
    ws = config.get("ai_assistant", "workspace") or ""
    if ws:
        return Path(ws)
    path = Path(config.data_dir) / _WORKSPACE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tadado_cli_path() -> str | None:
    """Frozen bundle: the sibling tadado-cli.exe (same-version instance)."""
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).parent / "tadado-cli.exe"
        if candidate.exists():
            return str(candidate)
    return None


def _launch_in_terminal(command: str, cwd: str) -> tuple[bool, str]:
    """Open a new terminal window running ``command`` in ``cwd``."""
    if shutil.which("wt"):  # Windows Terminal
        subprocess.Popen(
            ["wt", "-w", "0", "new-tab", "--startingDirectory", cwd,
             "cmd", "/k", command],
        )
        return True, "已在 Windows Terminal 启动"
    if sys.platform == "win32":
        subprocess.Popen(f'start "" cmd /k "{command}"', cwd=cwd, shell=True)
        return True, "已在新窗口启动"
    return False, "当前平台不支持从托盘启动终端"


def launch_session(config, partition_name: str = "") -> tuple[bool, str]:
    """Launch the dedicated AI-assistant session. Returns (ok, message).

    ``partition_name`` is the GUI's current partition — injected as
    TADADO_PARTITION so the session's CLI calls stay partition-scoped
    even when the model forgets to pass --partition explicitly.
    """
    provider = detect_provider(config)
    if provider is None:
        return False, "未检测到 Claude Code 或 Codex，AI 助手不可用"
    prompt = config.get("ai_assistant", "initial_prompt") or _DEFAULT_PROMPT
    workspace = _workspace_dir(config)
    quoted = prompt.replace('"', '\\"')
    command = f"{provider} \"{quoted}\""

    env = os.environ.copy()
    cli_exe = _tadado_cli_path()
    if cli_exe:
        env["TADADO_EXE"] = cli_exe  # skill 定位同版本 tadado-cli.exe
    if partition_name:
        env["TADADO_PARTITION"] = partition_name

    old_env = os.environ
    os.environ = env
    try:
        ok, message = _launch_in_terminal(command, str(workspace))
    finally:
        os.environ = old_env
    if ok:
        _log.info("AI assistant launched: provider=%s workspace=%s", provider, workspace)
    return ok, message
