"""QApplication subclass — startup orchestration."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import AppConfig
from .models.repository import TaskRepository
from .ui.main_window import MainWindow
from .ui.system_tray import SystemTrayManager
from .utils.signal_bus import get_signal_bus


class DeskTodoSeqApp(QApplication):
    """Main application — owns config, repository, and top-level UI."""

    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.setApplicationName("DeskTodoSeq")
        self.setApplicationVersion("0.1.0")
        self.setOrganizationName("DeskTodoSeq")
        self.setQuitOnLastWindowClosed(False)  # 关闭窗口时最小化到托盘

        # Core services
        self._config = AppConfig()
        self._repository = TaskRepository(self._config.db_path())
        self._repository.open()

        # Load theme early
        self._load_theme()

        # Signal bus
        self._signal_bus = get_signal_bus()
        self._signal_bus.application_quit.connect(self._on_quit)

        # UI
        self._main_window = MainWindow(self._config, self._repository)
        self._tray = SystemTrayManager(self._main_window, self._config)

        self._main_window.show()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _load_theme(self) -> None:
        theme_name = self._config.theme
        if theme_name == "system":
            theme_name = self._detect_system_theme()

        qss_path = self._resource_path("themes", f"{theme_name}.qss")
        if qss_path and qss_path.exists():
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            self.setStyleSheet("")

    @staticmethod
    def _detect_system_theme() -> str:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
        except Exception:
            return "light"

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    def _resource_path(self, *parts: str) -> Path | None:
        """Locate a resource file. Tries the source tree first, then PyInstaller _MEIPASS."""
        base = getattr(sys, "_MEIPASS", None)
        if base:
            path = Path(base) / "resources" / Path(*parts)
            if path.exists():
                return path
        path = Path(__file__).resolve().parents[1] / "resources" / Path(*parts)
        return path if path.exists() else None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def repository(self) -> TaskRepository:
        return self._repository

    @property
    def main_window(self) -> MainWindow:
        return self._main_window

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_quit(self) -> None:
        self._repository.close()
        self.quit()
