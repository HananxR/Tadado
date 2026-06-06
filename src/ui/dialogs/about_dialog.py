"""About dialog with feature overview and credits."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...utils.design_tokens import get_surface_color, is_dark
from ...utils.win32_theme import is_dark_mode_supported, set_window_dark_mode


_FEATURES = [
    ("📝 Markdown 任务", "Markdown 语法定义任务，支持优先级、截止时间、循环、标签"),
    ("📊 活动热力图", "GitHub 风格日历热力图，追踪每日任务完成情况"),
    ("🔒 分区隔离", "多分区独立管理，支持密码保护和自动锁定"),
    ("🏷 标签分类", "标签重命名、合并、全局同步，灵活归类"),
]


class AboutDialog(QDialog):
    """App information and feature overview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 Tadado")
        self.setObjectName("aboutDialog")
        self.resize(460, 500)
        self.setMinimumSize(420, 440)

        # --- Outer layout ---
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Scroll area for content ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(6)
        layout.setContentsMargins(28, 20, 28, 20)

        # --- Header ---
        # Logo
        logo_label = QLabel()
        logo_pixmap = QPixmap()
        import sys
        from pathlib import Path
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        logo_path = base / "resources" / "icons" / "app_icon.svg"
        if logo_path.exists():
            logo_pixmap = QPixmap(str(logo_path)).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
        if logo_pixmap.isNull():
            logo_label.setText("✨")
            logo_label.setStyleSheet("font-size: 48px;")
        else:
            logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo_label)

        name = QLabel("Tadado")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(name)

        version = QLabel("v1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        tagline = QLabel("Less noise. More done.")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet("font-size: 12px; color: palette(mid);")
        layout.addWidget(tagline)

        desc = QLabel(
            "Markdown 驱动的 Windows 桌面任务管理工具\n轻量、离线、专注于完成"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # --- Separator ---
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame { color: palette(mid); }")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # --- Feature list ---
        feat_title = QLabel("功能特性")
        feat_title.setStyleSheet("font-size: 13px; font-weight: bold; padding-top: 4px;")
        layout.addWidget(feat_title)

        for title, detail in _FEATURES:
            row = QLabel(f"<b>{title}</b>&nbsp;&nbsp;{detail}")
            row.setWordWrap(True)
            row.setStyleSheet("font-size: 11px; padding: 2px 0;")
            layout.addWidget(row)

        # --- Separator ---
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("QFrame { color: palette(mid); }")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # --- Footer ---
        repo = QLabel(
            '<a href="https://github.com/HananxR/Tadado"'
            ' style="color: palette(link);">'
            "github.com/HananxR/Tadado</a>"
        )
        repo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        repo.setOpenExternalLinks(True)
        repo.setStyleSheet("padding-top: 2px;")
        layout.addWidget(repo)

        license_label = QLabel("MIT License")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_label)

        author = QLabel("Hanxy <hanxy8413@gmail.com>")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author)

        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # --- Buttons ---
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)

    def showEvent(self, event: QShowEvent) -> None:
        """Apply dark title bar on Windows when the current theme is dark."""
        super().showEvent(event)
        if is_dark_mode_supported() and is_dark():
            set_window_dark_mode(self, True, caption_color=get_surface_color())
