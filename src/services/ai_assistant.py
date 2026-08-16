"""AI 助手启动器 — 从托盘启动专属 Claude Code / Codex 会话。

单 provider 架构：配置显式指定 claude/codex 之一；未配置时自动检测
（claude 优先）。两者都未安装 → AI 助手不可用。

会话续接：新会话启动后后台捕获会话 ID 存入配置；下次托盘点击可
`claude --resume <id>` / `codex resume <id>` 快速续接，不新开上下文。
上下文用量从会话 jsonl 的最后一个 usage 字段估算，超 80% 提示 compact。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

_log = logging.getLogger("runlog")

_WORKSPACE_DIR = "ai_workspace"
_DEFAULT_PROMPT = "/tadado 你好，我正在使用 Tadado AI 助手，请等待我的指令"
_CONTEXT_WINDOW_DEFAULT = 200_000  # claude-*/codex 当前上下文窗口（token）
_CONTEXT_ALERT_PERCENT = 80.0

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


def bundled_skill_path() -> Path:
    """软件随附 skill 路径（唯一权威源，用户编辑对象）.

    frozen（onedir）与 dev 均解析到应用目录的 resources/skill/tadado/SKILL.md；
    该目录随程序分发，且按用户权限安装（可写）。
    """
    import sys

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return base / "resources" / "skill" / "tadado" / "SKILL.md"


def ensure_bundled_skill() -> Path:
    """确保随附 skill 存在：缺失时用仓库 .claude 副本（dev）或内置模板初始化."""
    path = bundled_skill_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    dev_source = (
        Path(__file__).resolve().parents[3] / ".claude" / "skills" / "tadado" / "SKILL.md"
    )
    if dev_source.exists():
        path.write_text(dev_source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        path.write_text(
            "---\nversion: \"0.2.7\"\nname: tadado\ndescription: Tadado 任务管理\n---\n"
            "\n# Tadado Skill\n\n（默认模板，请按需编辑）\n",
            encoding="utf-8",
        )
    return path


def skill_version(path: Path) -> str:
    """读取 SKILL.md frontmatter 的 version 字段（无则返回空串）."""
    import re

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"^version:\s*[\"']?([^\"'\n]+)[\"']?$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _skill_host_paths() -> dict[str, Path]:
    """宿主 skill 目录：Claude Code 与 Codex 的用户级位置."""
    home = Path(os.path.expanduser("~"))
    return {
        "claude": home / ".claude" / "skills" / "tadado" / "SKILL.md",
        "codex": home / ".agents" / "skills" / "tadado" / "SKILL.md",
    }


def sync_skill_to_hosts() -> dict:
    """把随附 skill（权威源）分发到 Claude/Codex 宿主目录.

    返回 {host: bool(内容已与源一致)}。只有从这里分发的 skill 才生效。
    """
    source = ensure_bundled_skill()
    content = source.read_text(encoding="utf-8")
    result: dict = {}
    for host, target in _skill_host_paths().items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        result[host] = True
    return result


def skill_sync_status() -> dict:
    """随附 skill 的状态：路径、版本、各宿主是否已同步."""
    source = bundled_skill_path()
    exists = source.exists()
    version = skill_version(source) if exists else ""
    try:
        content = source.read_text(encoding="utf-8")
    except OSError:
        content = None
    synced: dict[str, bool] = {}
    for host, target in _skill_host_paths().items():
        if not target.exists() or content is None:
            synced[host] = False
            continue
        try:
            synced[host] = target.read_text(encoding="utf-8") == content
        except OSError:
            synced[host] = False
    return {"path": source, "exists": exists, "version": version, "synced": synced}


def _project_slug(path: str) -> str:
    """Claude Code 项目目录命名规则：非字母数字字符全部替换为 '-'."""
    return re.sub(r"[^0-9a-zA-Z]", "-", os.path.abspath(path))


def _sessions_dir(provider: str, workspace: str) -> Path:
    """宿主会话存储目录."""
    if provider == "codex":
        return Path(os.path.expanduser("~")) / ".codex" / "sessions"
    return Path(os.path.expanduser("~")) / ".claude" / "projects" / _project_slug(workspace)


def latest_session_id(provider: str, workspace: str) -> str | None:
    """最近的会话 ID（按 mtime），无会话返回 None."""
    d = _sessions_dir(provider, workspace)
    if not d.exists():
        return None
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].stem if files else None


def session_usage_percent(provider: str, workspace: str, session_id: str) -> float | None:
    """估算会话上下文用量百分比（最后一个 usage 字段 vs 上下文窗口）."""
    path = _sessions_dir(provider, workspace) / f"{session_id}.jsonl"
    if not path.exists():
        return None
    last_usage: dict | None = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                msg = d.get("message") if isinstance(d.get("message"), dict) else None
                if msg and isinstance(msg.get("usage"), dict):
                    last_usage = msg["usage"]
    except OSError:
        return None
    if not last_usage:
        return None
    total = (
        last_usage.get("input_tokens", 0)
        + last_usage.get("cache_read_input_tokens", 0)
        + last_usage.get("cache_creation_input_tokens", 0)
        + last_usage.get("output_tokens", 0)
    )
    return total / _CONTEXT_WINDOW_DEFAULT * 100.0


def capture_new_session(provider: str, workspace: str, before: float,
                        timeout: float = 60.0) -> str | None:
    """Poll for a session file newer than ``before`` (new session ID)."""
    d = _sessions_dir(provider, workspace)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if d.exists():
            for f in d.glob("*.jsonl"):
                try:
                    if f.stat().st_mtime > before:
                        return f.stem
                except OSError:
                    continue
        time.sleep(0.5)
    return None


def resume_command(provider: str, session_id: str) -> str:
    """续接会话的启动命令."""
    if provider == "codex":
        return f"codex resume {session_id}"
    return f"claude --resume {session_id}"


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


def _session_env(config, partition_name: str) -> dict:
    """会话环境：注入同版本 tadado-cli.exe 与当前分区兜底."""
    env = os.environ.copy()
    cli_exe = _tadado_cli_path()
    if cli_exe:
        env["TADADO_EXE"] = cli_exe  # skill 定位同版本 tadado-cli.exe
    if partition_name:
        env["TADADO_PARTITION"] = partition_name
    return env


def start_session(config, partition_name: str = "", resume: bool = False) -> tuple[bool, str]:
    """启动 AI 助手会话。Returns (ok, message).

    - ``resume=False``：新会话（首条指令自动加载 Tadado skill），后台捕获
      会话 ID 存入配置，供下次续接。
    - ``resume=True``：`claude --resume <id>` / `codex resume <id>` 续接上次
      会话；无会话记录时回退为新建。

    ``partition_name`` is the GUI's current partition — injected as
    TADADO_PARTITION so the session's CLI calls stay partition-scoped
    even when the model forgets to pass --partition explicitly.
    """
    provider = detect_provider(config)
    if provider is None:
        return False, "未检测到 Claude Code 或 Codex，AI 助手不可用"
    workspace = _workspace_dir(config)
    env = _session_env(config, partition_name)

    is_resume = resume
    if is_resume:
        session_id = config.get("ai_assistant", "session_id") or latest_session_id(
            provider, str(workspace)
        )
        if session_id:
            command = resume_command(provider, session_id)
        else:
            is_resume = False  # 无会话记录 → 新建

    if not is_resume:
        prompt = config.get("ai_assistant", "initial_prompt") or _DEFAULT_PROMPT
        quoted = prompt.replace('"', '\\"')
        command = f'{provider} "{quoted}"'
        before = time.time()

        def _capture() -> None:
            sid = capture_new_session(provider, str(workspace), before)
            if sid:
                config.set("ai_assistant", "session_id", value=sid)
                config.save()
                _log.info("AI assistant session captured: %s", sid)

        threading.Thread(target=_capture, daemon=True).start()

    old_env = os.environ
    os.environ = env
    try:
        ok, message = _launch_in_terminal(command, str(workspace))
    finally:
        os.environ = old_env
    if ok:
        _log.info("AI assistant launched: provider=%s resume=%s", provider, is_resume)
    return ok, message
