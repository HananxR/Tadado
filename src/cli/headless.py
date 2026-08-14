"""Headless CLI entry — forwards to a running GUI or executes in-process."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .commands import CliError, execute
from .output import render
from .parser import build_parser
from .protocol import LEGACY_EXIT_CODE

_ENV_DATA_DIR = "TADADO_DATA_DIR"


def _reconfigure_stdio() -> None:
    """Force UTF-8 stdio so Chinese output survives Windows console codepages."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _extract_format(argv: list[str]) -> tuple[list[str], str]:
    """Pop ``--format`` from anywhere in argv (before or after the subcommand)."""
    fmt = "json"
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--format" and i + 1 < len(argv):
            fmt = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--format="):
            fmt = arg.split("=", 1)[1]
            i += 1
            continue
        remaining.append(arg)
        i += 1
    return remaining, fmt


def run_cli(argv: list[str]) -> int:
    """Run one CLI invocation. Returns the process exit code."""
    _reconfigure_stdio()
    argv, fmt = _extract_format(argv)
    if fmt not in ("json", "human"):
        print(f"error: 无效输出格式: {fmt!r}（可选 json/human）", file=sys.stderr)
        return 2
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse prints usage itself
        return int(exc.code or 0)

    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication(["tadado-cli"])  # noqa: F841 — signals need an event core

    from ..config import AppConfig
    from ..models.repository import TaskRepository
    from ..services.task_service import TaskService
    from ..version import get_version

    env_dir = os.environ.get(_ENV_DATA_DIR)
    config = AppConfig(Path(env_dir)) if env_dir else AppConfig()

    # ── Path 1: forward to a running GUI instance (single-writer rule) ──────
    if not os.environ.get("TADADO_NO_FORWARD"):
        from .forward import try_forward

        request = {
            "v": 1,
            "app": get_version(),
            "data_dir": str(config.data_dir.resolve()),
            "command": args.command,
            "args": vars(args),
        }
        connected, response = try_forward(request)
        if connected:
            if response is None:
                print(
                    "error: Tadado GUI 正在运行但版本过旧（不支持 CLI），"
                    "请关闭 GUI 或升级到 0.2.7+",
                    file=sys.stderr,
                )
                return LEGACY_EXIT_CODE
            if response.get("ok"):
                print(render(response["result"], fmt))
                return 0
            print(f"error: {response.get('error', '未知错误')}", file=sys.stderr)
            return int(response.get("code", 1))

    # ── Path 2: headless execution over the same service seam as the GUI ────
    repository = TaskRepository(config.db_path())
    repository.open()
    try:
        service = TaskService(repository)
        result = execute(args.command, args, service, config)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    finally:
        repository.close()

    print(render(result, fmt))
    return 0
