"""ThemeRegistry —— 主题刷新注册表（弱引用）。

部件在构造末尾调用 :func:`register_theme_aware` 自助登记，主题切换时
:func:`refresh_theme_all` 一次性广播，MainWindow 不必再手工列举每一个部件，
新增部件也不会因为漏改中心分发点而丢失主题刷新。

注册表持**弱引用**：部件销毁后条目自动失效——既不阻止 GC，也不会在窗口
反复重建（如测试逐个创建 MainWindow）时累积陈旧条目。
"""

from __future__ import annotations

import weakref

__all__ = [
    "ThemeRegistry",
    "register_theme_aware",
    "refresh_theme_all",
    "theme_registry",
]


class ThemeRegistry:
    """登记带 ``refresh_theme()`` 的部件，并统一广播刷新。"""

    def __init__(self) -> None:
        self._refs: list[weakref.ref] = []

    def register(self, widget) -> None:
        """登记部件（幂等）。缺少 ``refresh_theme()`` 时抛 ``TypeError``。"""
        if not callable(getattr(widget, "refresh_theme", None)):
            raise TypeError(f"{widget!r} 未实现 refresh_theme()")
        self._prune()
        if any(ref() is widget for ref in self._refs):
            return
        self._refs.append(weakref.ref(widget))

    def refresh_all(self) -> None:
        """按注册顺序广播刷新；已销毁的部件自动跳过。"""
        self._prune()
        for ref in list(self._refs):  # 快照：刷新过程中可能发生注册
            widget = ref()
            if widget is not None:
                widget.refresh_theme()

    def clear(self) -> None:
        """清空注册表（测试隔离用）。"""
        self._refs.clear()

    def _prune(self) -> None:
        self._refs = [ref for ref in self._refs if ref() is not None]

    def __len__(self) -> int:
        return len([ref for ref in self._refs if ref() is not None])


_registry = ThemeRegistry()


def theme_registry() -> ThemeRegistry:
    """返回进程级注册表。"""
    return _registry


def register_theme_aware(widget) -> None:
    """把部件登记进全局注册表（部件构造末尾调用）。"""
    _registry.register(widget)


def refresh_theme_all() -> None:
    """广播主题刷新到全部已登记部件。"""
    _registry.refresh_all()
