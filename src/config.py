"""Application configuration — JSON-based with validation and hot-reload support."""

from __future__ import annotations

import copy
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

DEFAULT_CONFIG: dict = {
    "general": {
        "minimize_to_tray": True,
        "auto_start": False,
        "default_partition": "",
        "hidden_partitions": [],
        "last_partition_id": "",
        "page_size": 20,
        "default_sort": "urgency",
        "sort_completed_last": True,
        "hotkey": "Ctrl+Shift+Space",  # 全局唤醒热键（阶段 5）
        "pin_on_top": False,  # 常驻置顶（阶段 5）
        "timeline_range": "week",  # 时间轴默认粒度 week / month / 30d
        "auto_collapse_drawer": True,  # 维护抽屉保存后自动收起
    },
    "display": {
        "theme": "light",  # light / dark / system（跟随系统应用模式）
        "heatmap_start_year": 2026,
        "heatmap_color_scheme": "sunbeam",
    },
    "reminders": {
        "enabled": False,
        "daily_digest_time": "09:00",
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
    },
    "archive": {
        "enabled": False,
    },
    "ai_assistant": {
        "provider": "",  # "" = 自动检测（claude 优先）；显式 "claude" / "codex"
        "claude_cmd": "claude",
        "codex_cmd": "codex",
        "initial_prompt": "/tadado 你好，我正在使用 Tadado AI 助手，请等待我的指令",
        "workspace": "",  # 空 = 数据目录下 ai_workspace/
        "session_id": "",  # 上次会话 ID，托盘「继续上次会话」续接
        "resume": True,  # 启动助手时自动续接上次会话
        "usage_alert": True,  # 会话上下文超 80% 时提醒 /compact
        "inject_env": True,  # 注入 TADADO_EXE / TADADO_PARTITION 环境变量
    },
}


def _default_data_dir() -> Path:
    """Always use resources/ next to the source tree (portable-first)."""
    return Path(__file__).resolve().parents[1] / "resources"


def _is_frozen() -> bool:
    """True when running as a PyInstaller or Nuitka bundle."""
    return getattr(os.sys, "frozen", False) or "__compiled__" in dir(sys)


def _migrate_old_database(data_dir: Path) -> None:
    """Rename tasks.db → tadado.data if the old file exists and new doesn't."""
    old_db = data_dir / "tasks.db"
    new_db = data_dir / "tadado.data"
    if old_db.exists() and not new_db.exists():
        old_db.rename(new_db)


class AppConfig(QObject):
    """Application configuration with JSON persistence and change notification."""

    config_changed = Signal()

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        super().__init__()
        self._data_dir = data_dir or _default_data_dir()
        self._data: dict = {}
        self._log = logging.getLogger("runlog")
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
            except json.JSONDecodeError:
                self._log.warning("Config JSON decode error at %s, using defaults", config_path)
                self._data = {}
            except OSError as exc:
                self._log.warning("Config read error at %s: %s", config_path, exc)
                self._data = {}
        # Merge with defaults for any missing keys
        self._data = _deep_merge(DEFAULT_CONFIG, self._data)
        self._log.info("Config loaded from %s", config_path)
        _migrate_old_database(self._data_dir)

    def save(self) -> None:
        """Persist current config to disk."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._log.error("Failed to save config: %s", exc)
            return
        self._log.info("Config saved to %s", self._config_path())
        self.config_changed.emit()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def db_path(self) -> str:
        return str(self._data_dir / "tadado.data")

    def _config_path(self) -> Path:
        return self._data_dir / "config.json"

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def theme_mode(self) -> str:
        """配置里的原始取值：``"light"`` / ``"dark"`` / ``"system"``。

        设置面板的「主题」分段控件绑定的是它——三段都要能回显，
        不能用下面已解析过的 :attr:`theme`。
        """
        return self._get("display", "theme") or "light"

    @property
    def theme(self) -> str:
        """当前**生效**的主题：``"light"`` 或 ``"dark"``。

        ``display.theme = "system"`` 时按 Windows「应用模式」即时解析，
        因此所有既有消费方（design_tokens / 标题栏 / QSS）无需改动，
        只认 light/dark 即可。
        """
        mode = self.theme_mode
        if mode == "system":
            from .utils.win32_theme import system_prefers_dark

            return "dark" if system_prefers_dark() else "light"
        return mode

    @property
    def auto_collapse_drawer(self) -> bool:
        """维护抽屉保存后是否自动收起。"""
        return bool(self._get("general", "auto_collapse_drawer"))

    @property
    def timeline_range(self) -> str:
        """时间轴默认粒度：``week`` / ``month`` / ``30d``。"""
        return self._get("general", "timeline_range") or "week"

    @property
    def minimize_to_tray(self) -> bool:
        return bool(self._get("general", "minimize_to_tray"))

    @property
    def auto_start(self) -> bool:
        return bool(self._get("general", "auto_start"))

    @property
    def default_sort(self) -> str:
        return self._get("general", "default_sort")

    @property
    def sort_completed_last(self) -> bool:
        return bool(self._get("general", "sort_completed_last"))

    @property
    def reminders_enabled(self) -> bool:
        return bool(self._get("reminders", "enabled"))

    @property
    def reminder_daily_digest_time(self) -> str:
        return str(self._get("reminders", "daily_digest_time") or "09:00")

    @property
    def archive_enabled(self) -> bool:
        return bool(self._get("archive", "enabled"))

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
    """Recursively merge override into base. Returns a new dict.

    The base is deep-copied so instances never share (or mutate) the
    process-global DEFAULT_CONFIG nested dicts — even when ``override``
    is empty, a shallow copy would still leak the nested references.
    """
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result
