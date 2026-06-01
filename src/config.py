"""Application configuration — JSON-based with validation and hot-reload support."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal


DEFAULT_CONFIG: dict = {
    "general": {
        "language": "zh_CN",
        "auto_start": False,
        "minimize_to_tray": True,
        "default_partition": "",
        "hidden_partitions": [],
        "last_partition_id": "",
        "auto_lock_minutes": 10,
        "page_size": 20,
        "default_sort": "status",
    },
    "display": {
        "theme": "system",
        "font_size": 12,
        "heatmap_start_year": 2026,
        "heatmap_colors": {"levels": 8},
        "max_heatmap_tags": 3,
    },
    "reminders": {
        "enabled": True,
        "intervals_minutes": [30, 60, 1440],
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
    },
    "archive": {
        "enabled": False,
    },
    "hotkeys": {
        "toggle_window": "Ctrl+Alt+T",
        "new_task": "Ctrl+N",
    },
    "statuses": {},
    "progress_bar": {
        "enabled_periods": ["yesterday", "today", "last_week", "week", "last_month", "month"],
    },
    "deadline_calculator": {
        "default_type": "temporary",
        "weekly_day": 5,
        "weekly_next_week": False,
        "monthly_end_of_month": True,
    },
    "motd": {
        "today": "今日无事，宜放松身心 🌿",
        "week": "本周清风徐来，按自己的节奏前行 🚶",
        "overdue": "无挂碍事，一身轻松，快乐生活 ✨",
        "all": "一张白纸，正好画你想要的生活 🎨",
    },
}


def _default_data_dir() -> Path:
    """Always use resources/ next to the source tree (portable-first)."""
    return Path(__file__).resolve().parents[1] / "resources"


def _is_frozen() -> bool:
    """True when running as a PyInstaller or Nuitka bundle."""
    return getattr(os.sys, "frozen", False) or "__compiled__" in dir(sys)


def _migrate_old_database(data_dir: Path) -> None:
    """Rename tasks.db → desktodoseq.data if the old file exists and new doesn't."""
    old_db = data_dir / "tasks.db"
    new_db = data_dir / "desktodoseq.data"
    if old_db.exists() and not new_db.exists():
        old_db.rename(new_db)


class AppConfig(QObject):
    """Application configuration with JSON persistence and change notification."""

    config_changed = Signal()

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        super().__init__()
        self._data_dir = data_dir or _default_data_dir()
        self._data: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load config from JSON file, falling back to defaults."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        config_path = self._config_path()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        # Merge with defaults for any missing keys
        self._data = _deep_merge(DEFAULT_CONFIG, self._data)
        _migrate_old_database(self._data_dir)

    def save(self) -> None:
        """Persist current config to disk."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._config_path(), "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        self.config_changed.emit()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def db_path(self) -> str:
        return str(self._data_dir / "desktodoseq.data")

    def _config_path(self) -> Path:
        return self._data_dir / "config.json"

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def language(self) -> str:
        return self._get("general", "language")

    @property
    def theme(self) -> str:
        return self._get("display", "theme")

    @property
    def font_size(self) -> int:
        return int(self._get("display", "font_size"))

    @property
    def minimize_to_tray(self) -> bool:
        return bool(self._get("general", "minimize_to_tray"))

    @property
    def default_sort(self) -> str:
        return self._get("general", "default_sort")

    @property
    def heatmap_colors(self) -> dict:
        return dict(self._get("display", "heatmap_colors"))

    @property
    def reminders_enabled(self) -> bool:
        return bool(self._get("reminders", "enabled"))

    @property
    def reminder_intervals(self) -> list[int]:
        return list(self._get("reminders", "intervals_minutes"))

    @property
    def archive_enabled(self) -> bool:
        return bool(self._get("archive", "enabled"))

    @property
    def progress_enabled_periods(self) -> list[str]:
        return list(self._get("progress_bar", "enabled_periods"))

    @property
    def deadline_calculator_config(self) -> dict:
        return dict(self._data.get("deadline_calculator", {}))

    # ------------------------------------------------------------------
    # Getters / Setters
    # ------------------------------------------------------------------

    def get(self, *keys: str, default=None):
        """Deep get into nested dict, e.g. config.get('display', 'theme')."""
        node = self._data
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k, {})
            else:
                return default
        return node if node != {} else default

    def set(self, *keys: str, value) -> None:
        """Deep set and optionally persist.

        Usage: config.set('display', 'theme', value='dark')
        """
        node = self._data
        for k in keys[:-1]:
            if k not in node:
                node[k] = {}
            node = node[k]
        node[keys[-1]] = value

    def to_dict(self) -> dict:
        """Return a deep copy of all config data."""
        return json.loads(json.dumps(self._data))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, section: str, key: str):
        return self._data.get(section, {}).get(key)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Returns a new dict."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
