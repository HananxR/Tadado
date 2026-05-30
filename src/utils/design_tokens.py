"""Semantic design tokens for theme-aware coloring.

All hardcoded colors in the app should reference tokens from this module
via get_tokens(), so that switching between light and dark themes updates
every component consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtGui import QColor, QPalette


@dataclass(frozen=True)
class DesignTokens:
    """Semantic color roles for the application."""

    # ── Backgrounds ───────────────────────────────────────────────
    bg_primary: str           # main window / page background
    bg_secondary: str         # card / input field background
    bg_tertiary: str          # hover / pressed background
    bg_welcome_fallback: str  # welcome banner when no bg image

    # ── Text ──────────────────────────────────────────────────────
    text_primary: str         # body / heading text
    text_secondary: str       # meta / hint text (e.g. "#888")
    text_disabled: str        # disabled / placeholder text
    text_welcome_accent: str  # welcome banner "宜/忌" + "今日无事"
    text_welcome_sub: str     # welcome banner subtitle
    text_on_accent: str       # text drawn on accent background

    # ── Borders ───────────────────────────────────────────────────
    border_primary: str       # default border
    border_focus: str         # focus ring border

    # ── Semantic colours ──────────────────────────────────────────
    accent: str               # primary accent (blue)
    accent_hover: str
    danger: str               # destructive action (red)
    danger_hover: str
    danger_bg: str            # danger button background
    success: str              # completion (green)

    # ── Heatmap ────────────────────────────────────────────────────
    heatmap_empty: str         # cell with no tasks

    # ── Misc ──────────────────────────────────────────────────────
    separator: str            # horizontal rule / divider
    timeline_dot: str         # default timeline dot colour
    timeline_done: str        # timeline dot for completed entries

    # ── Methods ────────────────────────────────────────────────────

    def heatmap_gradient(self, levels: int = 8) -> list[str]:
        """Cool gradient: deep indigo → vivid blue → bright cyan.

        Produces a 'glowing' heatmap effect. Index 0 is the darkest/emptiest,
        index -1 is the brightest/most active.
        """
        from PySide6.QtGui import QColor as _QColor
        # Fixed cool-toned stops (not dependent on accent/bg_primary)
        stops = [
            (25, 30, 60),     # deep navy (empty)
            (40, 55, 120),    # dark blue
            (55, 90, 180),    # medium blue
            (70, 130, 220),   # light blue
            (90, 165, 240),   # sky blue
            (120, 195, 250),  # pale blue
            (60, 210, 220),   # teal
            (0, 230, 200),    # bright cyan (max activity)
        ]
        result: list[str] = []
        for i in range(levels):
            idx = i * (len(stops) - 1) / max(levels - 1, 1)
            lo = int(idx)
            hi = min(lo + 1, len(stops) - 1)
            frac = idx - lo
            r = int(stops[lo][0] + (stops[hi][0] - stops[lo][0]) * frac)
            g = int(stops[lo][1] + (stops[hi][1] - stops[lo][1]) * frac)
            b_val = int(stops[lo][2] + (stops[hi][2] - stops[lo][2]) * frac)
            result.append(f"#{r:02x}{g:02x}{b_val:02x}")
        return result


# ── Light palette ──────────────────────────────────────────────────────────

LIGHT_TOKENS = DesignTokens(
    bg_primary="#f5f4f0",
    bg_secondary="#fafaf8",
    bg_tertiary="#f0eee8",
    bg_welcome_fallback="#fffdf7",
    text_primary="#2c2c2c",
    text_secondary="#888",
    text_disabled="#ccc",
    text_welcome_accent="#c0392b",
    text_welcome_sub="#eee",
    text_on_accent="#ffffff",
    border_primary="#ddd9d0",
    border_focus="#5b8def",
    accent="#5b8def",
    accent_hover="#4a7de0",
    danger="#c0392b",
    danger_hover="#e07070",
    danger_bg="#fdf0ef",
    success="#27ae60",
    heatmap_empty="#dad6cc",
    separator="#e0ddd6",
    timeline_dot="#f39c12",
    timeline_done="#27ae60",
)

# ── Dark palette ───────────────────────────────────────────────────────────

DARK_TOKENS = DesignTokens(
    bg_primary="#1a1b26",
    bg_secondary="#1e1f2e",
    bg_tertiary="#2f3040",
    bg_welcome_fallback="#1a1b26",
    text_primary="#c9d1d9",
    text_secondary="#8b949e",
    text_disabled="#7a7c94",
    text_welcome_accent="#ff7675",
    text_welcome_sub="#a0a4b0",
    text_on_accent="#1a1b26",
    border_primary="#3d3f52",
    border_focus="#7aa2f7",
    accent="#7aa2f7",
    accent_hover="#5b8def",
    danger="#e07070",
    danger_hover="#c05050",
    danger_bg="#362430",
    success="#27ae60",
    heatmap_empty="#35374a",
    separator="#2f3040",
    timeline_dot="#f39c12",
    timeline_done="#27ae60",
)

# ── Singleton access ───────────────────────────────────────────────────────

_tokens: Optional[DesignTokens] = None
_config_ref: Optional[object] = None


def get_tokens() -> DesignTokens:
    """Return the current theme's design tokens.

    Returns LIGHT_TOKENS until :func:`init_tokens` is called with an
    AppConfig instance.
    """
    global _tokens
    if _tokens is None:
        _tokens = LIGHT_TOKENS
    return _tokens


def is_dark() -> bool:
    """Return True when the current theme is dark."""
    return get_tokens() is DARK_TOKENS


def init_tokens(config: object) -> None:
    """Bind token resolution to an AppConfig instance.

    After this call, :func:`get_tokens` will automatically track the
    configured theme.
    """
    global _config_ref
    _config_ref = config
    _resolve()


def refresh_tokens() -> None:
    """Re-resolve tokens from the bound config (call after theme change)."""
    _resolve()


def _resolve() -> None:
    global _tokens
    if _config_ref is None:
        _tokens = LIGHT_TOKENS
        return

    theme_name: str = _config_ref.theme  # type: ignore[union-attr]
    if theme_name == "system":
        # mirror app._detect_system_theme logic
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            theme_name = "light" if value == 1 else "dark"
        except Exception:
            theme_name = "light"

    _tokens = DARK_TOKENS if theme_name == "dark" else LIGHT_TOKENS


# ── QPalette builders ────────────────────────────────────────────────────────


def build_palette() -> QPalette:
    """Return a complete QPalette for the current theme.

    After calling :func:`QApplication.setPalette` with the result,
    every standard Qt widget will use theme-appropriate colours
    without needing QSS ``color`` or ``background-color`` rules.
    """
    t = get_tokens()
    p = QPalette()

    # Window
    p.setColor(QPalette.ColorRole.Window, QColor(t.bg_primary))
    p.setColor(QPalette.ColorRole.WindowText, QColor(t.text_primary))

    # Base (text edits, table cells, etc.)
    p.setColor(QPalette.ColorRole.Base, QColor(t.bg_secondary))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(t.bg_tertiary))
    p.setColor(QPalette.ColorRole.Text, QColor(t.text_primary))

    # Buttons
    p.setColor(QPalette.ColorRole.Button, QColor(t.bg_tertiary))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(t.text_primary))

    # Highlights (selection)
    p.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(t.text_on_accent))

    # Links
    p.setColor(QPalette.ColorRole.Link, QColor(t.accent))
    p.setColor(QPalette.ColorRole.LinkVisited, QColor(t.accent_hover))

    # Tooltip
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.bg_secondary))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(t.text_primary))

    # BrightText (used for e.g. selected tab text on Windows)
    p.setColor(QPalette.ColorRole.BrightText, QColor(t.danger))

    # Placeholder text
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_disabled))

    # Disabled states
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(t.text_disabled))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.text_disabled))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t.text_disabled))

    return p
