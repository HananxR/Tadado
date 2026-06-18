"""Logging infrastructure — daily rotation, 3-day retention, thread-safe.

Provides a single ``"runlog"`` logger that writes to ``resources/loginfo/tadado.log``.
The file rotates at midnight (TimedRotatingFileHandler) and keeps at most
3 old log files.  Call :func:`setup_logging` once at startup; thereafter use
:func:`get_logger` (or ``logging.getLogger("runlog")``) anywhere.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_LOG_DIR: Path | None = None
_LOGGER_NAME = "runlog"
_initialized = False


def _get_log_dir() -> Path:
    """Resolve ``resources/loginfo/`` for both frozen and dev runs."""
    global _LOG_DIR
    if _LOG_DIR is not None:
        return _LOG_DIR
    base = getattr(sys, "_MEIPASS", None)
    if base:
        _LOG_DIR = Path(base) / "resources" / "loginfo"
    else:
        _LOG_DIR = Path(__file__).resolve().parents[2] / "resources" / "loginfo"
    return _LOG_DIR


def setup_logging() -> logging.Logger:
    """Initialise the ``"runlog"`` logger with a daily-rotating file handler.

    Idempotent — subsequent calls are no-ops.  Returns the configured logger.
    """
    global _initialized
    logger = logging.getLogger(_LOGGER_NAME)

    if _initialized:
        return logger

    log_dir = _get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    # Clear any handlers that may have been added by a previous (e.g. test) call
    logger.handlers.clear()

    # ── File handler: midnight rotation, 3 backups ──────────────────────
    log_path = log_dir / "tadado.log"
    file_handler = TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        interval=1,
        backupCount=3,
        encoding="utf-8",
        delay=False,  # open immediately so we know the path works
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    # ── Console handler: DEBUG for dev convenience ──────────────────────
    if not getattr(sys, "frozen", False) and "__compiled__" not in dir(sys):
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.DEBUG)
        console.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(console)

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    _initialized = True
    return logger


def get_logger() -> logging.Logger:
    """Return the ``"runlog"`` logger, calling :func:`setup_logging` if needed."""
    if not _initialized:
        setup_logging()
    return logging.getLogger(_LOGGER_NAME)
