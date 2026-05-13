"""Theme-aware icon loader — loads appropriate icons for light/dark themes."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap


def _resource_path(*parts: str) -> Path:
    """Locate a resource file relative to the project root."""
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "resources" / Path(*parts)
    return Path(__file__).resolve().parents[2] / "resources" / Path(*parts)


class IconLoader:
    """Loads icons from resources/icons/ with optional theme awareness."""

    def __init__(self) -> None:
        self._cache: dict[str, QIcon] = {}

    def icon(self, name: str) -> QIcon:
        """Return a QIcon for the given icon name (without extension)."""
        cache_key = name
        if cache_key in self._cache:
            return self._cache[cache_key]

        icon = QIcon()
        sizes = [16, 24, 32, 48, 256]
        for sz in sizes:
            path = _resource_path("icons", f"{name}_{sz}.png")
            if path.exists():
                icon.addPixmap(QPixmap(str(path)))
        # Fallback: use the default size
        if icon.isNull():
            path = _resource_path("icons", f"{name}.png")
            if path.exists():
                icon.addPixmap(QPixmap(str(path)))

        self._cache[cache_key] = icon
        return icon

    def app_icon(self) -> QIcon:
        """Return the application icon (from ICO file)."""
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
