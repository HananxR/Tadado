"""Themed startup shield — covers the main window during initialization.

Uses the welcome-page background image (``welcome_bg.jpg``) as a backdrop
with a semi-transparent theme-colour overlay for text readability.

Sized to match the main window exactly so the title-bar region where DWM
ghost buttons flash is always covered.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
    QPixmap,
    QScreen,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# ---------------------------------------------------------------------------
# Chinese weekday names for date display
# ---------------------------------------------------------------------------
_WEEKDAY_CN = [
    "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app_icon_path() -> str:
    """Locate app_icon.svg — works both dev and PyInstaller frozen modes."""
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / "resources" / "icons" / "app_icon.svg"
    else:
        p = Path(__file__).resolve().parents[2] / "resources" / "icons" / "app_icon.svg"
    return p.as_posix() if p.exists() else ""


def _welcome_bg_path() -> str:
    """Locate welcome_bg.jpg — mirrors task_edit_panel._welcome_bg_path()."""
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / "resources" / "welcome_bg.jpg"
    else:
        p = Path(__file__).resolve().parents[2] / "resources" / "welcome_bg.jpg"
    return p.as_posix() if p.exists() else ""


# ---------------------------------------------------------------------------
# StartupShield
# ---------------------------------------------------------------------------


class StartupShield(QWidget):
    """Full-window overlay shown during startup to mask DWM ghost frames.

    Paints the welcome-page background image with a theme-coloured overlay
    so text remains readable in both light and dark themes.
    """

    _ICON_SIZE = 100

    def __init__(self, is_dark: bool, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # ── theme palette ──────────────────────────────────────────
        if is_dark:
            self._bg = QColor("#24253a")
            self._fg = QColor("#c9d1d9")
            self._accent = QColor("#7aa2f7")
            self._sub = QColor("#8b949e")
            self._overlay_alpha = 140  # ~55%
        else:
            self._bg = QColor("#ffffff")
            self._fg = QColor("#2c2c2c")
            self._accent = QColor("#5b8def")
            self._sub = QColor("#999999")
            self._overlay_alpha = 170  # ~67%

        # ── preload welcome background ─────────────────────────────
        bg_path = _welcome_bg_path()
        self._bg_pixmap = QPixmap(bg_path) if bg_path else QPixmap()
        self._scaled_bg: QPixmap | None = None

        # ── build UI widgets ───────────────────────────────────────
        self._build_ui()

    # ------------------------------------------------------------------
    # Background painting (mirrors task_edit_panel's _BannerWidget)
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # 1. background image — fill, crop excess
        if not self._bg_pixmap.isNull():
            if self._scaled_bg is None:
                self._scaled_bg = self._bg_pixmap.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            p.drawPixmap(0, 0, self._scaled_bg)
        else:
            p.setBrush(QBrush(self._bg))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(0, 0, w, h)

        # 2. semi-transparent overlay for text readability
        overlay = QColor(self._bg.red(), self._bg.green(), self._bg.blue(),
                         self._overlay_alpha)
        p.setBrush(QBrush(overlay))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(0, 0, w, h)

        p.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._scaled_bg = None  # invalidate cached scaled pixmap

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- top accent bar --
        accent_bar = QLabel()
        accent_bar.setFixedHeight(3)
        accent_bar.setStyleSheet(
            f"background-color: {self._accent.name()}; border: none;"
        )
        root.addWidget(accent_bar)

        # -- central content --
        root.addStretch(5)

        content = QWidget()
        content.setFixedWidth(400)
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # app icon — SVG rendered at target size for perfect sharpness
        icon_path = _app_icon_path()
        if icon_path:
            renderer = QSvgRenderer(icon_path)
            if renderer.isValid():
                icon = QLabel()
                pix = QPixmap(self._ICON_SIZE, self._ICON_SIZE)
                pix.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pix)
                renderer.render(painter)
                painter.end()
                icon.setPixmap(pix)
                icon.setFixedSize(self._ICON_SIZE, self._ICON_SIZE)
                icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                icon.setStyleSheet("background: transparent; border: none;")
                ic_wrapper = QVBoxLayout()
                ic_wrapper.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ic_wrapper.addWidget(icon)
                layout.addLayout(ic_wrapper)
                layout.addSpacing(22)

        # app name
        name = QLabel("TADADO")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setFont(QFont("Microsoft YaHei", 38, QFont.Weight.Bold))
        name.setStyleSheet(
            f"color: {self._fg.name()}; background: transparent;"
        )
        layout.addWidget(name)

        layout.addSpacing(8)

        # tagline
        tagline = QLabel("Less Noise, More Done")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setFont(QFont("Microsoft YaHei", 13))
        tagline.setStyleSheet(
            f"color: {self._accent.name()}; background: transparent;"
        )
        layout.addWidget(tagline)

        layout.addSpacing(20)

        # current date
        now = datetime.now()
        date_str = (
            f"{now.year}年{now.month}月{now.day}日 "
            f"{_WEEKDAY_CN[now.weekday()]}"
        )
        date_label = QLabel(date_str)
        date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        date_label.setFont(QFont("Microsoft YaHei", 12))
        date_label.setStyleSheet(
            f"color: {self._sub.name()}; background: transparent;"
        )
        layout.addWidget(date_label)

        layout.addSpacing(28)

        # decorative separator — accent diamond between thin lines
        sep = QLabel(
            f'<span style="color:{self._sub.name()};font-size:10px;">'
            f'━  </span>'
            f'<span style="color:{self._accent.name()};font-size:11px;">'
            f'&#9670;</span>'   # ◆
            f'<span style="color:{self._sub.name()};font-size:10px;">'
            f'  ━</span>'
        )
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep.setStyleSheet("background: transparent;")
        sep.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(sep)

        layout.addSpacing(10)

        # loading text
        loading = QLabel("正在加载…")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setFont(QFont("Microsoft YaHei", 10))
        loading.setStyleSheet(
            f"color: {self._sub.name()}; background: transparent;"
        )
        layout.addWidget(loading)

        cw = QVBoxLayout()
        cw.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cw.addWidget(content)
        root.addLayout(cw)

        root.addStretch(7)

        # -- version --
        ver_label = QLabel("v0.1.0")
        ver_label.setFont(QFont("Microsoft YaHei", 8))
        ver_label.setStyleSheet(
            f"color: {self._sub.name()}; background: transparent; "
            "padding: 8px 14px;"
        )
        ver_wrapper = QVBoxLayout()
        ver_wrapper.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom
        )
        ver_wrapper.addWidget(ver_label)
        root.addLayout(ver_wrapper)

    # ------------------------------------------------------------------
    # Geometry (mirrors MainWindow.apply_screen_size)
    # ------------------------------------------------------------------

    def match_main_window_geometry(self) -> None:
        """Resize and position to exactly cover the main window area."""
        self.setMinimumSize(900, 600)
        screen: QScreen | None = self.screen()
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1050, 680)
            return
        geom = screen.availableGeometry()
        w = min(int(geom.width() * 0.65), 1400)
        h = min(int(geom.height() * 0.72), 900)
        self.resize(w, h)
        self.move(
            geom.x() + (geom.width() - w) // 2,
            geom.y() + (geom.height() - h) // 2,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dismiss(self) -> None:
        """Close the shield and schedule for deletion."""
        self.close()
        self.deleteLater()
