"""System tray icon with context menu."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..config import AppConfig
from ..utils.icon_loader import get_icon_loader


class SystemTrayManager:
    """Manages the system tray icon and its context menu."""

    def __init__(self, main_window, config: AppConfig) -> None:
        self._main_window = main_window
        self._config = config

        icon = get_icon_loader().app_icon()
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("Tadado")

        self._build_menu()
        self._tray.activated.connect(self._on_activated)
        # show() 延迟到主窗口显示后调用，避免 QSystemTrayIcon 内部 HWND
        # 在主窗口之前闪现为"小窗口残影"（Windows 已知行为）

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()

        show_action = menu.addAction("显示/隐藏窗口")
        show_action.triggered.connect(self._toggle_window)

        menu.addSeparator()

        new_action = menu.addAction("新建单任务")
        new_action.triggered.connect(self._main_window._on_menu_new_draft)

        multi_action = menu.addAction("新建多任务")
        multi_action.triggered.connect(self._main_window._on_menu_new_multi)

        menu.addSeparator()

        # AI 助手入口：菜单构建一次，展开时原位刷新检测状态。
        # 注意：不可在 aboutToShow 里重建/替换整个菜单——Windows 上会
        # 取消正在弹出的菜单，表现为点击无反应。
        self._ai_action = menu.addAction("AI 助手")
        self._ai_action.triggered.connect(self._launch_ai_assistant)
        self._refresh_ai_action()

        menu.addSeparator()

        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._main_window._on_quit)

        menu.aboutToShow.connect(self._refresh_ai_action)
        self._tray.setContextMenu(menu)

    def _refresh_ai_action(self) -> None:
        """In-place refresh of the AI action's availability label."""
        provider = self._detect_ai_provider()
        if provider is None:
            self._ai_action.setEnabled(False)
            self._ai_action.setText("AI 助手（未检测到 Claude/Codex）")
            self._ai_action.setToolTip(
                "安装 Claude Code 或 Codex 后可用，或检查配置 ai_assistant.provider"
            )
        else:
            self._ai_action.setEnabled(True)
            self._ai_action.setText(f"AI 助手（{provider.capitalize()}）")
            self._ai_action.setToolTip(f"启动专属 {provider} 会话，自动加载 Tadado skill")

    def show(self) -> None:
        """Show the tray icon (called after main window appears to avoid flash)."""
        self._tray.show()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _detect_ai_provider(self) -> str | None:
        """Single-provider detection: claude/codex — None when unavailable."""
        try:
            from ..services.ai_assistant import detect_provider

            return detect_provider(self._config)
        except Exception as exc:
            from ..utils.log_manager import setup_logging

            setup_logging().warning("AI assistant detection failed: %s", exc)
            return None

    def _launch_ai_assistant(self) -> None:
        from ..services.ai_assistant import launch_session

        partition = self._main_window.active_partition_name()
        ok, message = launch_session(self._config, partition_name=partition)
        if ok:
            self.show_message("AI 助手", f"{message}\n首条指令已自动加载 Tadado skill")
        else:
            self.show_message("AI 助手", message)

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
