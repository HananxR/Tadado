"""Semantic design tokens for theme-aware coloring.

All hardcoded colors in the app should reference tokens from this module
via get_tokens(), so that switching between light and dark themes updates
every component consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtGui import QColor, QFont, QPalette


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
    bg_primary="#f4f3ef",
    bg_secondary="#ecebe5",
    bg_tertiary="#e6e4dc",
    bg_welcome_fallback="#fdf9ef",
    surface_raised="#ffffff",
    text_primary="#38362f",
    text_secondary="#6e6a5e",
    text_disabled="#a29c8c",
    text_welcome_accent="#c0392b",
    text_welcome_sub="#eee",
    text_on_accent="#ffffff",
    border_primary="#e3dfd3",
    border_focus="#4c56c0",
    accent="#4c56c0",
    accent_hover="#40499f",
    danger="#c24536",
    danger_hover="#b03a2c",
    danger_bg="#f6e4e0",
    success="#3c8d5e",
    warning="#c07f2d",
    heatmap_empty="#e4dfd3",
    separator="#ece8de",
    timeline_dot="#c07f2d",
    timeline_done="#3c8d5e",
    urgency_urgent="#c24536",
    urgency_high="#c07f2d",
    urgency_medium="#3c8d5e",
    urgency_normal="#8ba0c0",
)

# ── Dark palette ───────────────────────────────────────────────────────────

DARK_TOKENS = DesignTokens(
    bg_primary="#1b1c26",
    bg_secondary="#181921",
    bg_tertiary="#212230",
    bg_welcome_fallback="#1b1c26",
    surface_raised="#272834",
    text_primary="#c9c5b7",
    text_secondary="#8b8675",
    text_disabled="#676258",
    text_welcome_accent="#ff7675",
    text_welcome_sub="#a0a4b0",
    text_on_accent="#eceaf4",
    border_primary="#2e2f3e",
    border_focus="#7b83e8",
    accent="#7b83e8",
    accent_hover="#939af1",
    danger="#e26b5b",
    danger_hover="#ec8078",
    danger_bg="#3a2622",
    success="#78bd92",
    warning="#dfa24e",
    heatmap_empty="#2c2d3a",
    separator="#2c2d3a",
    timeline_dot="#dfa24e",
    timeline_done="#78bd92",
    urgency_urgent="#e26b5b",
    urgency_high="#dfa24e",
    urgency_medium="#78bd92",
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


def surface_color(dark: bool) -> str:
    """卡片底色（原型 ``--surface``）。

    ``DesignTokens`` 数据类里**没有**这个字段——它是派生色，而 QSS（通过
    ``{{surface}}``）和 QPalette（``AlternateBase``）都要用，所以在这里
    单点定义，避免两处各写一份十六进制字面量后走样。
    """
    return "#21222f" if dark else "#fbfaf6"


def border_2_color(dark: bool) -> str:
    """控件描边色（原型 ``--border-2``）；同 :func:`surface_color` 的理由。"""
    return "#3b3c4c" if dark else "#d3cebf"


def apply_display_font(
    label,
    *,
    tracking: Optional[float] = None,
    tabular: bool = False,
) -> None:
    """给展示层文字补上 QSS **表达不了**的两个排版属性。

    Qt QSS 的字体属性只有 ``font-family / font-size / font-style /
    font-weight`` 这四项。原型里的

      * ``letter-spacing:1px``（``.set-sec-t`` / ``.rail-group`` eyebrow 小标签）
      * ``font-variant-numeric: tabular-nums``（``.tile .num`` 统计数字，
        让「1」和「8」等宽，数值刷新时不会左右抖动）
      * ``line-height:1.6``

    **都不在支持列表内**，写进 QSS 会被静默丢弃——这解释了为什么字距一直
    没生效。它们只能落到 ``QFont``：``setLetterSpacing`` 与 OpenType
    feature ``tnum``。

    :param tracking: 字距，单位 px（原型 eyebrow 用 1、页面标题用 .2）
    :param tabular: 是否启用等宽数字（统计数字 / 时长列）
    """
    font = QFont(label.font())
    if tracking is not None:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking)
    if tabular:
        # QFont.setFeature 与 QFont.Tag 需要 Qt 6.7+；低版本静默跳过，
        # 只是数字不等宽，不影响正确性。
        set_feature = getattr(font, "setFeature", None)
        tag_factory = getattr(QFont, "Tag", None)
        if set_feature is not None and tag_factory is not None:
            set_feature(tag_factory("tnum"), 1)
    label.setFont(font)


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
        # ── 2.0 原型令牌（`tadado-2.0.html` 的 --surface / --border-2 / 语义软色）──
        # 原型把「卡片底色」与「页面底色」分成 --surface / --surface-2 两层，
        # 我们此前只有一层 surface_raised，这里补齐以免卡片与页面糊成一片。
        "surface": surface_color(dark),
        "border_2": border_2_color(dark),
        "hover": "rgba(123,131,232,0.12)" if dark else "rgba(76,86,192,0.06)",
        "accent_soft": "#262a4d" if dark else "#e8e9f7",
        "danger_soft": "#3a2622" if dark else "#f6e4e0",
        "todo": "#6f9fe0" if dark else "#3d6fb5",
        "todo_soft": "#223049" if dark else "#e2eaf5",
        "doing": "#dfa24e" if dark else "#c07f2d",
        "doing_soft": "#3a2f1e" if dark else "#f6ead9",
        "done": "#78bd92" if dark else "#3c8d5e",
        "done_soft": "#1f3328" if dark else "#e0efe5",
        "sus": "#8d8675",
        "sus_soft": "#2b2a24" if dark else "#eceae3",
        # ── 字体栈 ──────────────────────────────────────────────────────
        # 仅适配 Windows，因此不再把 ``Noto Sans SC`` 放在首位（本机恰好
        # 装了才没露馅，换台机器就会掉回默认字体）。改为 Windows 的
        # ``system-ui`` 等价物：拉丁字母走 Segoe UI，中文落到 Microsoft
        # YaHei UI——这正是浏览器在 Windows 上的回退顺序，也是「web 感」
        # 的来源之一。YaHei UI 比 YaHei 行高更紧，更适合 UI。
        "font_body": '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif',
        # 展示层：Windows 上 Segoe UI 的粗体是**独立字族**（Semibold/Bold），
        # 用它可拿到真实的半粗字形，而不是 Regular 的合成伪粗。
        "font_disp": '"Segoe UI Semibold", "Segoe UI", "Microsoft YaHei UI", sans-serif',
        "font_mono": '"Cascadia Code", "Cascadia Mono", Consolas, monospace',
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


# ── 高度 / 投影 ─────────────────────────────────────────────────
# 原型靠 ``--shadow`` 建立层次，而 **QSS 没有 box-shadow**，Qt 只能用
# ``QGraphicsDropShadowEffect`` 逐部件施加。原型是两段式
# （``0 10px 32px -8px`` 大范围柔光 + ``0 2px 8px`` 近距接触影），
# 一个部件却只能挂一个效果，这里用单段近似：blur 取原型外层的量级，
# dy 取内层的克制值，避免小部件被大投影糊住。
#
# 阴影色刻意用**暖黑** ``rgb(40,36,28)`` 而不是纯黑——纯黑落在暖灰纸底
# （``bg_primary #f4f3ef``）上会发脏、发青；暖黑才是原型的观感。

#: 三档高度：``{blur, dy, alpha}``；``alpha`` 为 ``(亮色, 暗色)``
ELEVATION: dict[int, dict] = {
    0: {"blur": 0, "dy": 0, "alpha": (0, 0)},          # 无投影
    1: {"blur": 16, "dy": 2, "alpha": (26, 88)},       # 卡片 / 热力图
    2: {"blur": 26, "dy": 6, "alpha": (40, 110)},      # hover 浮起 / 浮层
    3: {"blur": 36, "dy": 10, "alpha": (58, 132)},     # 弹层 / 抽屉
}

#: 记录档位的动态属性名（供 :func:`refresh_elevation` 在换主题后重放）
ELEVATION_PROP = "elevationLevel"

#: 阴影投影在部件外所需的留白（≈ blur 的一半），布局要留出这个余量
def elevation_pad(level: int) -> int:
    """该档位投影需要向外预留的像素（blur/2 向上取整）。"""
    spec = ELEVATION.get(int(level), ELEVATION[0])
    return -(-spec["blur"] // 2)


def elevation_params(level: int) -> dict:
    """当前主题下该档位的投影参数 ``{blur, dy, color}``。"""
    from PySide6.QtGui import QColor

    dark = is_dark()
    spec = ELEVATION.get(int(level), ELEVATION[0])
    alpha = spec["alpha"][1] if dark else spec["alpha"][0]
    return {
        "blur": spec["blur"],
        "dy": spec["dy"],
        "color": QColor(0, 0, 0, alpha) if dark else QColor(40, 36, 28, alpha),
    }


def apply_elevation(widget, level: int = 1) -> None:
    """给 ``widget`` 挂上第 ``level`` 档投影（``0`` = 清除）。

    注意：投影画在部件边界**之外**，需要所在布局留出
    :func:`elevation_pad` 的余量，否则会被父部件裁掉。
    """
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    widget.setProperty(ELEVATION_PROP, int(level))
    if int(level) <= 0:
        widget.setGraphicsEffect(None)
        return

    p = elevation_params(level)
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(p["blur"])
    effect.setOffset(0, p["dy"])
    effect.setColor(p["color"])
    widget.setGraphicsEffect(effect)


def refresh_elevation(widget) -> None:
    """换主题后按 ``ELEVATION_PROP`` 重放投影（阴影色随明暗变化）。"""
    level = widget.property(ELEVATION_PROP)
    if level is None:
        return
    apply_elevation(widget, int(level))


def apply_card_shadow(widget) -> None:
    """卡片默认投影——等价 :func:`apply_elevation` 第 1 档（保留旧入口名）。"""
    apply_elevation(widget, 1)


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

    # Base（文本编辑、表格/列表视口等）
    # 注意：bg_secondary/bg_tertiary 在原型里是**凹槽色**，只用于分段控件
    # 轨道。把它们当通用底色会让所有没被 QSS 覆盖的部件（表头、viewport、
    # 交替行、单选框）发灰发暗——这是"总有一层蒙版"的第二来源。
    # 通用表面一律用 surface_raised（纯白）/ surface（卡片）。
    p.setColor(QPalette.ColorRole.Base, QColor(t.surface_raised))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(surface_color(is_dark())))
    p.setColor(QPalette.ColorRole.Text, QColor(t.text_primary))

    # Buttons
    p.setColor(QPalette.ColorRole.Button, QColor(t.surface_raised))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(t.text_primary))

    # Highlights (selection)
    p.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(t.text_on_accent))

    # Links
    p.setColor(QPalette.ColorRole.Link, QColor(t.accent))
    p.setColor(QPalette.ColorRole.LinkVisited, QColor(t.accent_hover))

    # Tooltip
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.surface_raised))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(t.text_primary))

    # ── 压平 Fusion 的斜面 / 渐变 ──────────────────────────────────────
    # Fusion 是**调色板驱动**的风格：按钮与面板上的高光、阴影不是画死的
    # 位图，而是拿 Light / Midlight / Mid / Dark / Shadow 这几个角色与
    # Button 做明暗插值算出来的。QPalette() 默认构造留给它们的是一套冷灰
    # 值，结果每个「没被 QSS 完全接管」的控件——工具按钮、SpinBox 上下
    # 箭头、滚动条、进度条槽、GroupBox、表头、Splitter——都自带一层由上
    # 到下的渐变。这才是那股「蒙版感 / 发灰」的真正来源：
    # 它不来自我们的配色，而是来自 Fusion 内置的第二套明暗。
    #
    # 把这几个角色对齐到 Button 同色，插值两端相等，渐变在源头塌成纯色。
    # 相比逐个 widget 补 QSS，这是一次生效且覆盖全部控件的做法。
    # 立体感改由 Shadow 提供 1px 描边——与原型「用 border 而非斜面
    # 表达层级」（.card 只有 border 没有 box-shadow）的语言一致。
    flat = QColor(t.surface_raised)
    for _role in (
        QPalette.ColorRole.Light,
        QPalette.ColorRole.Midlight,
        QPalette.ColorRole.Mid,
        QPalette.ColorRole.Dark,
    ):
        p.setColor(_role, flat)
    p.setColor(QPalette.ColorRole.Shadow, QColor(t.border_primary))

    # BrightText (used for e.g. selected tab text on Windows)
    p.setColor(QPalette.ColorRole.BrightText, QColor(t.danger))

    # Placeholder text
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_disabled))

    # Disabled states
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(t.text_disabled))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.text_disabled))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t.text_disabled))

    return p
