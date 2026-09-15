"""ThemeRegistry —— 弱引用主题刷新注册表（阶段 7）。"""

from __future__ import annotations

import gc

import pytest

from src.utils.theme_registry import ThemeRegistry, refresh_theme_all, theme_registry


class _Widget:
    def __init__(self) -> None:
        self.calls = 0

    def refresh_theme(self) -> None:
        self.calls += 1


class TestThemeRegistry:
    def test_refresh_all_calls_every_registered(self):
        reg = ThemeRegistry()
        a, b = _Widget(), _Widget()
        reg.register(a)
        reg.register(b)

        reg.refresh_all()

        assert (a.calls, b.calls) == (1, 1)

    def test_register_is_idempotent(self):
        reg = ThemeRegistry()
        w = _Widget()
        reg.register(w)
        reg.register(w)
        assert len(reg) == 1

        reg.refresh_all()
        assert w.calls == 1

    def test_dead_widgets_are_dropped(self):
        reg = ThemeRegistry()
        w = _Widget()
        reg.register(w)
        assert len(reg) == 1

        del w
        gc.collect()

        assert len(reg) == 0
        reg.refresh_all()  # 已销毁的条目不应再被调用

    def test_rejects_widget_without_refresh_theme(self):
        reg = ThemeRegistry()
        with pytest.raises(TypeError):
            reg.register(object())

    def test_global_registry_helpers(self):
        reg = theme_registry()
        reg.clear()
        try:
            w = _Widget()
            reg.register(w)
            refresh_theme_all()
            assert w.calls == 1
        finally:
            reg.clear()
