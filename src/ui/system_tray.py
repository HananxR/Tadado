"""System tray icon with context menu."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
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

        # 上下文用量巡检：超 80% 提醒 /compact（每个会话只提醒一次）
        # 注意：SystemTrayManager 不是 QObject，QTimer 需挂到托盘图标上。
        self._alerted_session: str | None = None
        self._ctx_timer = QTimer(self._tray)
        self._ctx_timer.setInterval(60_000)
        self._ctx_timer.timeout.connect(self._check_context_usage)
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

        # AI 助手入口：自动续接上次会话（无记录则新建），无需用户选择。
        # 菜单构建一次，展开时原位刷新检测状态——不可在 aboutToShow 里
        # 重建/替换整个菜单（Windows 上会取消弹出，表现为点击无反应）。
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
        from ..services.ai_assistant import (
            _workspace_dir,
            latest_session_id,
            session_usage_percent,
        )

        provider = self._detect_ai_provider()
        if provider is None:
            self._ai_action.setEnabled(False)
            self._ai_action.setText("AI 助手（未检测到 Claude/Codex）")
            self._ai_action.setToolTip(
                "安装 Claude Code 或 Codex 后可用，或检查配置 ai_assistant.provider"
            )
            return
        self._ai_action.setEnabled(True)
        label = f"AI 助手（{provider.capitalize()}）"
        workspace = str(_workspace_dir(self._config))
        session_id = self._config.get("ai_assistant", "session_id") or latest_session_id(
            provider, workspace
        )
        if session_id:
            pct = session_usage_percent(provider, workspace, session_id)
            if pct is not None and pct >= 80:
                label = f"AI 助手（上下文 {pct:.0f}%，建议 /compact）"
        self._ai_action.setText(label)
        self._ai_action.setToolTip("自动续接上次会话（无记录则新建），自动加载 Tadado skill")

    def show(self) -> None:
        """Show the tray icon (called after main window appears to avoid flash)."""
        self._tray.show()
        self._ctx_timer.start()

    def _check_context_usage(self) -> None:
        """Periodic: remind the user to /compact when context exceeds 80%."""
        from ..services.ai_assistant import (
            _workspace_dir,
            latest_session_id,
            session_usage_percent,
        )

        provider = self._detect_ai_provider()
        if provider is None:
            return
        workspace = str(_workspace_dir(self._config))
        session_id = self._config.get("ai_assistant", "session_id") or latest_session_id(
            provider, workspace
        )
        if not session_id:
            return
        pct = session_usage_percent(provider, workspace, session_id)
        if pct is not None and pct >= 80 and session_id != self._alerted_session:
            self._alerted_session = session_id
            self.show_message(
                "AI 助手",
                f"会话上下文已使用 {pct:.0f}%，建议在会话中输入 /compact 压缩上下文",
            )

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
        """自动操作：有会话记录则续接，无记录则新建（start_session 内置回退）."""
        from ..services.ai_assistant import start_session

        partition = self._main_window.active_partition_name()
        ok, message = start_session(self._config, partition_name=partition, resume=True)
        if ok:
            self.show_message("AI 助手", f"{message}\n已自动续接会话并加载 Tadado skill")
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
