"""Centralized version source — single point of truth for the app version.

The canonical version lives here.  ``release.ps1`` sets the git tag from
the same value, and ``pyproject.toml`` should be kept in sync manually
(used only by the build backend).

Usage::

    from src.version import __version__, get_version_display

"""

from __future__ import annotations

__version__ = "0.1.0"


def get_version() -> str:
    """Return the raw semver string, e.g. ``"0.1.0"``."""
    return __version__


def get_version_display() -> str:
    """Return the user-facing version string, e.g. ``"v0.1.0"``."""
    return f"v{__version__}"


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a version string like ``"v1.2.3"`` or ``"1.2.3"`` into a tuple."""
    clean = version_str.lstrip("v").strip()
    parts = clean.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version_str!r}")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]
