"""Theme-aware icon loader — draws icons at runtime using design_tokens color."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPixmap

from ..ui.icon_draw import ICON_DRAW_FUNCS


def _resource_path(*parts: str) -> Path:
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "resources" / Path(*parts)
    return Path(__file__).resolve().parents[2] / "resources" / Path(*parts)


class _ThemedIconEngine(QIconEngine):
    """Icon engine that draws icons at runtime using the current theme color."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        draw_func = ICON_DRAW_FUNCS.get(self._name)
        if draw_func is None:
            return
        from .design_tokens import get_tokens
        color = QColor(get_tokens().text_primary)

        # Slightly dim when disabled
        if mode == QIcon.Mode.Disabled:
            color.setAlpha(100)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw within the target rect, preserving aspect ratio
        target = QRectF(rect)
        draw_func(painter, target, color)

        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        px = QPixmap(size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        self.paint(p, QRect(QPoint(0, 0), size), mode, state)
        p.end()
        return px

    def clone(self) -> QIconEngine:
        return _ThemedIconEngine(self._name)

    def key(self) -> str:
        return f"ThemedIconEngine:{self._name}"


class IconLoader:
    """Loads icons drawn at runtime with theme-aware colors. Caches QIcon instances."""

    def __init__(self) -> None:
        self._cache: dict[str, QIcon] = {}

    def icon(self, name: str) -> QIcon:
        if name in self._cache:
            return self._cache[name]
        # File-based icon takes priority (PNG/SVG in resources/icons/)
        icon = QIcon()
        for ext in (".svg", ".png"):
            path = _resource_path("icons", f"{name}{ext}")
            if path.exists():
                icon = QIcon(str(path))
                self._cache[name] = icon
                return icon
        # Fallback to runtime-drawn icon (theme-aware)
        if name in ICON_DRAW_FUNCS:
            engine = _ThemedIconEngine(name)
            icon = QIcon(engine)
        self._cache[name] = icon
        return icon

    def app_icon(self) -> QIcon:
        path = _resource_path("icons", "app.ico")
        if path.exists():
            return QIcon(str(path))
        return self.icon("app")

    def clear_cache(self) -> None:
        self._cache.clear()


_loader: IconLoader | None = None


def get_icon_loader() -> IconLoader:
    global _loader
    if _loader is None:
        _loader = IconLoader()
    return _loader


def load_icon(name: str) -> QIcon:
    return get_icon_loader().icon(name)
