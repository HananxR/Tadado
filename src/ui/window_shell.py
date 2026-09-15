"""WindowShell —— 窗口「唤醒 / 置顶 / 全局热键」的唯一入口（仅 Windows 全功能）。

收编原先散落在 MainWindow 与 SystemTrayManager 中的
``show() + setWindowState(...) + raise_() + activateWindow()`` 序列，
并统一管理：

* 全局热键（:mod:`src.utils.win32_hotkey`）—— 通过原生事件过滤器消费
  ``WM_HOTKEY``（:data:`HOTKEY_MESSAGE`）
* 常驻置顶（``WindowStaysOnTopHint``）

设计约束：``__init__`` **不注册热键**，由 app.py 在启动完成后显式调用
:meth:`install_hotkey`，避免测试进程占用系统级热键。
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, Signal
from PySide6.QtWidgets import QMainWindow, QWidget

from ..config import AppConfig
from ..utils import win32_hotkey

# 注意：不要在模块导入期调用 setup_logging()——否则 CLI 进程一旦间接导入本模块，
# 日志会被挂到 stdout 并污染 `--cli` 的 JSON 输出（回归见 test_cli e2e）。
_log = logging.getLogger("runlog")


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    """把 ``WM_HOTKEY`` 转成 Qt 信号（仅 Windows 会真正收到消息）。"""

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == win32_hotkey.HOTKEY_MESSAGE:
                    self._callback()
                    return True, 0
        except Exception:  # pragma: no cover - 原生消息解析失败不应崩溃
            pass
        return False, 0


class WindowShell(QObject):
    """窗口生命周期收敛层。

    Signals:
        hotkey_triggered(): 全局热键被按下
    """

    hotkey_triggered = Signal()

    def __init__(
        self,
        window: QMainWindow,
        config: AppConfig,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._window = window
        self._config = config
        self._pinned = False
        self._hotkey_filter: Optional[_HotkeyEventFilter] = None
        self._hotkey_registered = False

    # ------------------------------------------------------------------
    # 唤醒 / 显隐
    # ------------------------------------------------------------------

    def wake(self, switch_to: str | None = None) -> None:
        """显示、去最小化、置前并聚焦；``switch_to`` 可同时切换页面。"""
        if switch_to and hasattr(self._window, "_switch_view"):
            self._window._switch_view(switch_to)
        self._window.show()
        self._window.setWindowState(
            self._window.windowState() & ~Qt.WindowState.WindowMinimized
        )
        self._window.raise_()
        self._window.activateWindow()

    def hide_to_tray(self) -> None:
        self._window.hide()

    def toggle_visibility(self) -> None:
        """托盘双击 / 菜单「显示/隐藏窗口」。"""
        if self._window.isVisible() and not self._window.isMinimized():
            self._window.hide()
        else:
            self.wake()

    # ------------------------------------------------------------------
    # 常驻置顶
    # ------------------------------------------------------------------

    @property
    def is_pinned(self) -> bool:
        return self._pinned

    def set_pinned(self, enabled: bool) -> None:
        self._pinned = bool(enabled)
        self._window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._pinned)
        # 改变窗口标志会隐藏窗口（Qt 语义），需重新显示
        if self._window.isVisible():
            self._window.show()

    def apply_configured_pin(self) -> None:
        """启动时套用 ``general.pin_on_top``。"""
        try:
            enabled = bool(self._config.get("general", "pin_on_top"))
        except Exception:  # pragma: no cover - 配置缺失时保持默认
            enabled = False
        if enabled:
            self.set_pinned(True)

    # ------------------------------------------------------------------
    # 全局热键
    # ------------------------------------------------------------------

    @property
    def hotkey_registered(self) -> bool:
        return self._hotkey_registered

    @property
    def hotkey_accel(self) -> str:
        try:
            return str(self._config.get("general", "hotkey") or "")
        except Exception:  # pragma: no cover
            return ""

    def install_hotkey(self, accel: str | None = None) -> bool:
        """注册全局热键并在 Windows 上安装原生事件过滤器。

        非 Windows、配置为空或注册失败时返回 False（不影响其他功能）。
        """
        accel = (accel if accel is not None else self.hotkey_accel).strip()
        if not accel or not win32_hotkey.is_supported():
            return False

        if self._hotkey_filter is None:
            from PySide6.QtCore import QCoreApplication

            self._hotkey_filter = _HotkeyEventFilter(self._on_hotkey)
            app = QCoreApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self._hotkey_filter)

        ok = win32_hotkey.register_hotkey(accel, self._on_hotkey)
        self._hotkey_registered = bool(ok)
        if ok:
            _log.info("WindowShell: global hotkey registered (%s)", accel)
        else:
            _log.warning("WindowShell: failed to register hotkey %r", accel)
        return self._hotkey_registered

    def _on_hotkey(self) -> None:
        self.hotkey_triggered.emit()
        self.wake()

    def shutdown(self) -> None:
        """注销热键并移除原生事件过滤器（app 退出时调用，幂等）。"""
        if self._hotkey_registered:
            win32_hotkey.unregister_hotkey()
            self._hotkey_registered = False
        if self._hotkey_filter is not None:
            from PySide6.QtCore import QCoreApplication

            app = QCoreApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._hotkey_filter)
            self._hotkey_filter = None


def shell_for(widget: QWidget) -> Optional[WindowShell]:
    """便捷取用：从 MainWindow 上取已创建的 shell。"""
    return getattr(widget, "_window_shell", None)
