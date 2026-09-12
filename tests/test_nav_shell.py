"""NavShell qtbot 测试 — 分组渲染、点击信号、Ctrl+1..5、设置齿轮。"""

from __future__ import annotations

from src.ui.nav_shell import NavShell
from src.ui.views import VIEW_REGISTRY


def _make(qtbot) -> NavShell:
    shell = NavShell()
    qtbot.addWidget(shell)
    return shell


def test_has_five_page_buttons(qtbot):
    shell = _make(qtbot)
    assert list(shell._buttons.keys()) == list(VIEW_REGISTRY.keys())


def test_click_emits_page_requested(qtbot):
    shell = _make(qtbot)
    seen: list[str] = []
    shell.page_requested.connect(seen.append)
    shell._buttons["analysis"].click()
    assert seen == ["analysis"]
    assert shell.active == "analysis"


def test_set_active_highlights(qtbot):
    shell = _make(qtbot)
    shell.set_active("tasks")
    assert shell.active == "tasks"
    assert shell._buttons["tasks"].property("active") is True
    assert shell._buttons["overview"].property("active") is not True


def test_shortcuts(qtbot):
    """Ctrl+N 快捷键 → 注册表第 N 页（offscreen 平台不投递真实按键，直接触发激活信号）。"""
    shell = _make(qtbot)
    seen: list[str] = []
    shell.page_requested.connect(seen.append)
    shell._shortcuts[1].activated.emit()  # Ctrl+2 → 注册表第二个页面
    assert seen == ["tasks"]


def test_settings_gear(qtbot):
    shell = _make(qtbot)
    seen: list[int] = []
    shell.settings_requested.connect(lambda: seen.append(1))
    shell._settings_btn.click()
    assert seen == [1]
