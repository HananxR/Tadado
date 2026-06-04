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

    # ── Urgency / Priority ─────────────────────────────────────────
    urgency_urgent: str       # urgency bg: 紧急 (red)
    urgency_high: str         # urgency bg: 重要 (orange)
    urgency_medium: str       # urgency bg: 关注 (green)
    urgency_normal: str       # urgency bg: 普通 (light blue)

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
    urgency_urgent="#c0392b",
    urgency_high="#e67e22",
    urgency_medium="#27ae60",
    urgency_normal="#aed6f1",
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
    urgency_urgent="#e07070",
    urgency_high="#f0a060",
    urgency_medium="#2ecc71",
    urgency_normal="#5b8cbd",
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


def expand_qss(template: str) -> str:
    """Replace {{token}} placeholders in a QSS template with current theme values."""
    t = get_tokens()
    dark = t is DARK_TOKENS

    expansions = {
        # Core tokens
        "bg_primary": t.bg_primary,
        "bg_secondary": t.bg_secondary,
        "bg_tertiary": t.bg_tertiary,
        "text_primary": t.text_primary,
        "text_secondary": t.text_secondary,
        "text_disabled": t.text_disabled,
        "text_on_accent": t.text_on_accent,
        "border_primary": t.border_primary,
        "accent": t.accent,
        "accent_hover": t.accent_hover,
        "danger": t.danger,
        "danger_light": t.danger_hover,
        "danger_hover": "#c05050" if dark else "#e07070",
        "success": t.success,
        "white": "#ffffff",
        # Surface / structural
        "surface_raised": "#24253a" if dark else "#ffffff",
        "surface_alt": "#212236" if dark else "#fafaf8",
        "surface_dark": "#2a2b3a" if dark else "#f0eee8",
        "surface_hover": "#252638" if dark else "#f8f7f4",
        "selection_bg": "#2f3648" if dark else "#edf2fb",
        "selection_alt": "#2f4360" if dark else "#c5d8f8",
        "report_header": "#252636" if dark else "#fafaf8",
        "entry_hover": "#2a2b3c" if dark else "#f8f7f4",
        "entry_selected": "#253045" if dark else "#edf2fb",
        # Interactive states
        "hover_strong": "#44455a" if dark else "#e8e6e0",
        "hover_bg": "#383a50" if dark else "#e8e4dc",
        "pressed_bg": "#363850" if dark else "#e0ddd6",
        "text_muted": "#555770" if dark else "#aaa",
        "nav_secondary": "#8b8da0" if dark else "#999",
        "disabled_text": "#555" if dark else "#aaa",
        # Danger / destructive
        "danger_border": "#5c3038" if dark else "#e8c8c8",
        "danger_bg_dark": "#362430" if dark else "#fdf0ef",
        # Overlay / alpha
        "overlay_8": "rgba(128,128,128,0.08)",
        "overlay_35": "rgba(128,128,128,0.35)",
        "accent_alpha_13": "rgba(122,162,247,0.13)" if dark else "rgba(91,139,239,0.13)",
        "bg_primary_alpha_235": "rgba(26,27,38,235)" if dark else "rgba(245,244,240,235)",
        "border_alpha_25": "rgba(61,63,82,0.25)" if dark else "rgba(221,217,208,0.25)",
    }
    result = template
    for name, value in expansions.items():
        result = result.replace(f"{{{{{name}}}}}", value)
    return result


def is_dark() -> bool:
    """Return True when the current theme is dark."""
    return get_tokens() is DARK_TOKENS


def get_surface_color() -> str:
    """Return the raised-surface background color for the current theme.

    This is the background used by the custom title bar / menu bar area,
    useful for matching native window decorations.
    """
    return "#24253a" if is_dark() else "#ffffff"


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
