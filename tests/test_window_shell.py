"""WindowShell 测试 —— 唤醒/显隐/置顶/热键生命周期（阶段 5）。"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow

from src.config import AppConfig
from src.ui.window_shell import WindowShell


@pytest.fixture
def shell(tmp_path, qapp, qtbot):
    config = AppConfig(tmp_path)
    window = QMainWindow()
    qtbot.addWidget(window)
    instance = WindowShell(window, config)
    yield instance, window, config
    instance.shutdown()


class TestWakeAndVisibility:
    def test_wake_shows_and_clears_minimized(self, shell):
        instance, window, config = shell
        window.showMinimized()
        instance.wake()
        assert window.isVisible()
        assert not (window.windowState() & Qt.WindowState.WindowMinimized)

    def test_wake_switches_view_when_supported(self, shell):
        instance, window, config = shell

        class _Stub(QMainWindow):
            def __init__(self):
                super().__init__()
                self.switched: list[str] = []

            def _switch_view(self, page: str) -> None:
                self.switched.append(page)

        stub = _Stub()
        try:
            stub_shell = WindowShell(stub, config)
            stub_shell.wake(switch_to="tasks")
            assert stub.switched == ["tasks"]
        finally:
            stub.deleteLater()

    def test_toggle_visibility_hides_then_shows(self, shell):
        instance, window, config = shell
        instance.wake()
        assert window.isVisible()
        instance.toggle_visibility()
        assert not window.isVisible()
        instance.toggle_visibility()
        assert window.isVisible()

    def test_hide_to_tray(self, shell):
        instance, window, config = shell
        instance.wake()
        instance.hide_to_tray()
        assert not window.isVisible()


class TestPin:
    def test_set_pinned_flag(self, shell):
        instance, window, config = shell
        assert instance.is_pinned is False
        instance.set_pinned(True)
        assert instance.is_pinned is True
        assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        instance.set_pinned(False)
        assert not (window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_apply_configured_pin_true(self, tmp_path, qapp, qtbot):
        config = AppConfig(tmp_path)
        config.set("general", "pin_on_top", value=True)
        window = QMainWindow()
        qtbot.addWidget(window)
        instance = WindowShell(window, config)
        try:
            instance.apply_configured_pin()
            assert instance.is_pinned is True
        finally:
            instance.shutdown()

    def test_apply_configured_pin_defaults_false(self, shell):
        instance, window, config = shell
        instance.apply_configured_pin()
        assert instance.is_pinned is False


class TestHotkey:
    def test_hotkey_accel_from_config(self, shell):
        instance, window, config = shell
        assert instance.hotkey_accel == "Ctrl+Shift+Space"

    def test_install_empty_accel_is_noop(self, shell):
        instance, window, config = shell
        assert instance.install_hotkey("") is False
        assert instance.hotkey_registered is False

    def test_install_invalid_accel_returns_false(self, shell):
        """非法加速器在任何平台都返回 False，且不会触碰系统注册表。"""
        instance, window, config = shell
        assert instance.install_hotkey("Ctrl+Foo") is False
        assert instance.hotkey_registered is False

    def test_install_on_non_windows_returns_false(self, shell, monkeypatch):
        instance, window, config = shell
        monkeypatch.setattr(sys, "platform", "linux")
        assert instance.install_hotkey() is False
        assert instance.hotkey_registered is False

    def test_shutdown_is_idempotent(self, shell):
        instance, window, config = shell
        instance.shutdown()
        instance.shutdown()
        assert instance.hotkey_registered is False

    def test_hotkey_trigger_wakes_window(self, shell):
        instance, window, config = shell
        window.hide()
        instance._on_hotkey()
        assert window.isVisible()
