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
    surface_raised: str       # elevated card surface (layering above bg_primary)

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
    warning: str              # time-sensitive warning (orange, <3h deadlines)

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
        """Return *levels* ``#RRGGBB`` colours from the current scheme.

        Index 0 is the empty-cell colour; indices 1..levels-1 form the
        activity gradient from low to high.
        """
        return _compute_heatmap_gradient(_current_scheme_key, is_dark(), levels)


# ── Heatmap colour schemes ──────────────────────────────────────────────────


@dataclass(frozen=True)
class HeatmapScheme:
    """Named colour scheme for the activity heatmap — 8 gradient stops.

    Stop 0 is the empty-cell colour; stops 1–7 are the activity gradient
    from low to high.
    """

    name: str
    gradient_stops: list[tuple[int, int, int]]  # 8 RGB triples


HEATMAP_SCHEMES: dict[str, dict[str, HeatmapScheme]] = {
    # 所有方案的空单元格统一为暖纸色（与 heatmap_empty 令牌一致），
    # 渐变终点锚定语义令牌：暖阳→warning 琥珀、新绿→success 绿、
    # 海洋→accent 品牌靛青、樱花→暖调玫瑰，确保与整体暖灰体系协调。
    "sunbeam": {
        "light": HeatmapScheme(
            "暖阳",
            [
                (228, 223, 213),  # empty: 暖纸
                (246, 232, 201),  # pale gold
                (247, 216, 156),  # golden straw
                (244, 194, 110),  # amber
                (236, 164, 64),   # warm amber
                (217, 127, 38),   # amber（对齐 warning）
                (191, 96, 32),    # deep amber
                (162, 78, 28),    # burnt amber
            ],
        ),
        "dark": HeatmapScheme(
            "暖阳",
            [
                (44, 45, 58),     # empty: 暖夜
                (70, 60, 44),     # dark amber
                (102, 80, 52),    # bronze
                (140, 105, 62),   # golden brown
                (184, 140, 74),   # gold
                (224, 170, 63),   # amber
                (240, 190, 80),   # bright amber
                (250, 214, 110),  # sun amber
            ],
        ),
    },
    "sprout": {
        "light": HeatmapScheme(
            "新绿",
            [
                (228, 223, 213),  # empty: 暖纸
                (214, 232, 208),  # pale sage
                (190, 224, 178),  # light green
                (158, 212, 146),  # medium-light green
                (120, 196, 118),  # medium green
                (84, 178, 102),   # green
                (56, 150, 86),    # green（对齐 success）
                (41, 124, 72),    # deep green
            ],
        ),
        "dark": HeatmapScheme(
            "新绿",
            [
                (44, 45, 58),     # empty: 暖夜
                (48, 66, 52),     # dark forest
                (54, 86, 60),     # medium-dark green
                (64, 112, 70),    # medium green
                (80, 142, 88),    # green
                (104, 172, 110),  # bright green
                (140, 196, 132),  # light green
                (190, 224, 170),  # pale green
            ],
        ),
    },
    "ocean": {
        "light": HeatmapScheme(
            "海洋",
            [
                (228, 223, 213),  # empty: 暖纸
                (214, 217, 235),  # pale periwinkle
                (190, 196, 228),  # light indigo
                (160, 170, 220),  # medium indigo
                (126, 138, 210),  # indigo
                (94, 108, 200),   # indigo（对齐 accent）
                (70, 82, 186),    # deep indigo
                (54, 64, 160),    # deep brand indigo
            ],
        ),
        "dark": HeatmapScheme(
            "海洋",
            [
                (44, 45, 58),     # empty: 暖夜
                (52, 55, 86),     # dark indigo
                (60, 66, 118),    # medium-dark indigo
                (72, 80, 148),    # medium indigo
                (92, 100, 178),   # indigo
                (116, 124, 208),  # bright indigo
                (142, 150, 228),  # light indigo（对齐 accent）
                (176, 182, 244),  # pale indigo
            ],
        ),
    },
    "sakura": {
        "light": HeatmapScheme(
            "樱花",
            [
                (228, 223, 213),  # empty: 暖纸
                (243, 224, 224),  # pale rose
                (240, 204, 208),  # light rose
                (234, 178, 188),  # medium rose
                (224, 148, 164),  # rose
                (210, 116, 140),  # deep rose
                (192, 88, 116),   # cherry
                (170, 64, 94),    # deep cherry
            ],
        ),
        "dark": HeatmapScheme(
            "樱花",
            [
                (44, 45, 58),     # empty: 暖夜
                (66, 50, 58),     # dark rose
                (92, 60, 70),     # medium-dark rose
                (124, 72, 84),    # medium rose
                (158, 88, 102),   # rose
                (190, 108, 124),  # soft rose
                (216, 134, 150),  # light rose
                (238, 164, 178),  # blossom rose
            ],
        ),
    },
}

_current_scheme_key: str = "sunbeam"


def _compute_heatmap_gradient(
    scheme_key: str, is_dark: bool, levels: int = 8
) -> list[str]:
    """Return *levels* ``#RRGGBB`` colours interpolated from a scheme's stops."""
    theme = "dark" if is_dark else "light"
    scheme = HEATMAP_SCHEMES.get(scheme_key, HEATMAP_SCHEMES["sunbeam"])[theme]
    stops = scheme.gradient_stops  # 8 RGB triples
    result: list[str] = []
    for i in range(levels):
        idx = i * (len(stops) - 1) / max(levels - 1, 1)
        lo = int(idx)
        hi = min(lo + 1, len(stops) - 1)
        frac = idx - lo
        r = int(stops[lo][0] + (stops[hi][0] - stops[lo][0]) * frac)
        g = int(stops[lo][1] + (stops[hi][1] - stops[lo][1]) * frac)
        b = int(stops[lo][2] + (stops[hi][2] - stops[lo][2]) * frac)
        result.append(f"#{r:02x}{g:02x}{b:02x}")
    return result


# ── Light palette ──────────────────────────────────────────────────────────

LIGHT_TOKENS = DesignTokens(
    bg_primary="#f6f4ef",
    bg_secondary="#fcfbf7",
    bg_tertiary="#efece3",
    bg_welcome_fallback="#fdf9ef",
    surface_raised="#fdfcf8",
    text_primary="#3a3832",
    text_secondary="#6f6a5f",
    text_disabled="#b8b3a6",
    text_welcome_accent="#c0392b",
    text_welcome_sub="#eee",
    text_on_accent="#ffffff",
    border_primary="#e3dfd4",
    border_focus="#4d57c3",
    accent="#4d57c3",
    accent_hover="#3f48b0",
    danger="#c4453c",
    danger_hover="#b03a32",
    danger_bg="#f9efed",
    success="#2f9e63",
    warning="#d97f26",
    heatmap_empty="#e4dfd3",
    separator="#ece8de",
    timeline_dot="#d97f26",
    timeline_done="#2f9e63",
    urgency_urgent="#c4453c",
    urgency_high="#d97f26",
    urgency_medium="#2f9e63",
    urgency_normal="#8ba0c0",
)

# ── Dark palette ───────────────────────────────────────────────────────────

DARK_TOKENS = DesignTokens(
    bg_primary="#1b1c26",
    bg_secondary="#232430",
    bg_tertiary="#2d2e3c",
    bg_welcome_fallback="#1b1c26",
    surface_raised="#272835",
    text_primary="#d8d5c9",
    text_secondary="#9d988b",
    text_disabled="#6e6a60",
    text_welcome_accent="#ff7675",
    text_welcome_sub="#a0a4b0",
    text_on_accent="#eceaf4",
    border_primary="#32333f",
    border_focus="#7c83ea",
    accent="#7c83ea",
    accent_hover="#8a90f0",
    danger="#e06c63",
    danger_hover="#ec8078",
    danger_bg="#3a252a",
    success="#3fae7c",
    warning="#e0963f",
    heatmap_empty="#2c2d3a",
    separator="#2c2d3a",
    timeline_dot="#e0963f",
    timeline_done="#3fae7c",
    urgency_urgent="#e06c63",
    urgency_high="#e0963f",
    urgency_medium="#3fae7c",
    urgency_normal="#5d7399",
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
        "surface_raised": t.surface_raised,
        "text_primary": t.text_primary,
        "text_secondary": t.text_secondary,
        "text_disabled": t.text_disabled,
        "text_on_accent": t.text_on_accent,
        "border_primary": t.border_primary,
        "accent": t.accent,
        "accent_hover": t.accent_hover,
        "danger": t.danger,
        "danger_light": t.danger_hover,
        "danger_hover": "#ec8078" if dark else "#b03a32",
        "success": t.success,
        "white": "#ffffff",
        # Surface / structural
        "surface_raised": "#272835" if dark else "#fdfcf8",
        "surface_alt": "#232430" if dark else "#fcfbf7",
        "surface_dark": "#2d2e3c" if dark else "#efece3",
        "surface_hover": "#272835" if dark else "#f3f1ea",
        "selection_bg": "#33364a" if dark else "#e8ebf7",
        "selection_alt": "#38405f" if dark else "#c2c9ef",
        "report_header": "#232430" if dark else "#fcfbf7",
        "entry_hover": "#2d2e3c" if dark else "#f3f1ea",
        "entry_selected": "#2f3349" if dark else "#e8ebf7",
        # Interactive states
        "hover_strong": "#3a3c4e" if dark else "#e9e5da",
        "hover_bg": "#33354a" if dark else "#ece8dd",
        "pressed_bg": "#31334a" if dark else "#e2ddd1",
        "text_muted": "#6e6a60" if dark else "#8a857a",
        "nav_secondary": "#9d988b" if dark else "#8a857a",
        "disabled_text": "#6e6a60" if dark else "#b8b3a6",
        # Danger / destructive
        "danger_border": "#57323a" if dark else "#ecc9c6",
        "danger_bg_dark": "#3a252a" if dark else "#f9efed",
        # Overlay / alpha
        "overlay_8": "rgba(128,128,128,0.08)",
        "overlay_35": "rgba(128,128,128,0.35)",
        "accent_alpha_13": "rgba(124,131,234,0.14)" if dark else "rgba(77,87,195,0.13)",
        "bg_primary_alpha_235": "rgba(27,28,38,235)" if dark else "rgba(246,244,239,235)",
        "border_alpha_25": "rgba(50,51,63,0.3)" if dark else "rgba(227,223,212,0.3)",
    }
    result = template
    for name, value in expansions.items():
        result = result.replace(f"{{{{{name}}}}}", value)
    return result


def status_color(status_value: str) -> str:
    """Token-based display color for a task status value (UI 展示用)."""
    t = get_tokens()
    mapping = {
        "TODO": t.accent,
        "DOING": t.warning,
        "DONE": t.success,
        "OVERDUE": t.danger,
    }
    return mapping.get(str(status_value).upper(), t.text_secondary)


def apply_card_shadow(widget) -> None:
    """Soft elevation shadow for card containers (theme-aware)."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(12)
    effect.setOffset(0, 1)
    effect.setColor(QColor(0, 0, 0, 45 if is_dark() else 28))
    widget.setGraphicsEffect(effect)


def is_dark() -> bool:
    """Return True when the current theme is dark."""
    return get_tokens() is DARK_TOKENS


def get_surface_color() -> str:
    """Return the raised-surface background color for the current theme.

    This is the background used by the custom title bar / menu bar area,
    useful for matching native window decorations.
    """
    return "#272835" if is_dark() else "#fdfcf8"


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
    global _tokens, _current_scheme_key
    if _config_ref is None:
        _tokens = LIGHT_TOKENS
        _current_scheme_key = "sunbeam"
        return

    theme_name: str = _config_ref.theme  # type: ignore[union-attr]
    _tokens = DARK_TOKENS if theme_name == "dark" else LIGHT_TOKENS
    _current_scheme_key = _config_ref.get(  # type: ignore[union-attr]
        "display", "heatmap_color_scheme", default="sunbeam"
    )


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
