"""System tray icon with context menu."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..config import AppConfig
from ..utils.icon_loader import load_icon


class SystemTrayManager:
    """Manages the system tray icon and its context menu."""

    def __init__(self, main_window, config: AppConfig) -> None:
        self._main_window = main_window
        self._config = config

        icon = load_icon("tray_normal")
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("DeskTodoSeq")

        self._build_menu()
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()

        show_action = menu.addAction("显示/隐藏窗口")
        show_action.triggered.connect(self._toggle_window)

        menu.addSeparator()

        new_action = menu.addAction("新建任务...")
        new_action.triggered.connect(self._main_window._on_new_task)

        menu.addSeparator()

        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._main_window._on_quit)

        self._tray.setContextMenu(menu)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _toggle_window(self) -> None:
        win = self._main_window
        if win.isVisible() and not win.isMinimized():
            win.hide()
        else:
            win.show()
            win.setWindowState(win.windowState() & ~Qt.WindowState.WindowMinimized)
            win.raise_()
            win.activateWindow()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def show_message(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    @staticmethod
    def _icon_path(name: str) -> str:
        import sys
        from pathlib import Path
        base = getattr(sys, "_MEIPASS", None)
        if base:
            path = Path(base) / "resources" / "icons" / name
        else:
            path = Path(__file__).resolve().parents[2] / "resources" / "icons" / name
        return str(path) if path.exists() else ""
