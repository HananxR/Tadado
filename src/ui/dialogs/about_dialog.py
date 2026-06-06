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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...utils.design_tokens import get_surface_color, is_dark
from ...utils.win32_theme import is_dark_mode_supported, set_window_dark_mode

_FEATURES = [
    ("📝 Markdown 任务管理", "语法创建，优先级、截止时间、循环、全文搜索"),
    ("📊 活动分析", "日历热力图、活动时间线、工作报告导出"),
    ("🔧 批量操作", "全选、右键批量变更状态、延后、中止、删除"),
    ("🏷 标签管理", "重命名、合并，全局自动同步"),
    ("🔒 分区管理", "多分区隔离，密码保护，自动锁定"),
    ("⏰ 智能提醒", "到期通知、免打扰安静时段、托盘弹窗"),
]


class AboutDialog(QDialog):
    """App information and feature overview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 Tadado")
        self.setObjectName("aboutDialog")
        self.resize(420, 480)
        self.setMinimumSize(380, 400)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)

        # ── Logo ──
        logo = QLabel()
        logo_path = self._find_icon("app_icon.svg")
        pix = QPixmap(logo_path) if logo_path else QPixmap()
        if not pix.isNull():
            pix = pix.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pix)
        else:
            logo.setText("✦")
            logo.setStyleSheet("font-size: 52px; color: #6366F1;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(14)

        # ── Name + version ──
        name = QLabel("Tadado")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(name)
        layout.addSpacing(2)

        ver = QLabel("v1.0.0  ·  Less noise. More done.")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("font-size: 12px; color: palette(mid);")
        layout.addWidget(ver)
        layout.addSpacing(18)

        # ── Separator ──
        layout.addWidget(_h_line())
        layout.addSpacing(14)

        # ── Feature list ──
        for title, desc in _FEATURES:
            row = QLabel(f'<b style="font-size:12px;">{title}</b>'
                         f'<span style="font-size:11px; color:palette(mid);"> &nbsp;—&nbsp; {desc}</span>')
            row.setWordWrap(True)
            layout.addWidget(row)
            layout.addSpacing(6)

        layout.addSpacing(6)

        # ── Separator ──
        layout.addWidget(_h_line())
        layout.addSpacing(14)

        # ── Footer ──
        repo = QLabel(
            '<a href="https://github.com/HananxR/Tadado" style="color: palette(link);">'
            "github.com/HananxR/Tadado</a>"
        )
        repo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        repo.setOpenExternalLinks(True)
        repo.setStyleSheet("font-size: 11px;")
        layout.addWidget(repo)

        foot = QLabel("MIT License  ·  Hanxy <hanxy8413@gmail.com>")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setStyleSheet("font-size: 11px; color: palette(mid);")
        layout.addWidget(foot)

        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.setCenterButtons(True)
        outer.addWidget(buttons)

    # ── helpers ──

    @staticmethod
    def _find_icon(name: str) -> str | None:
        import sys
        from pathlib import Path
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        p = base / "resources" / "icons" / name
        return str(p) if p.exists() else None

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if is_dark_mode_supported() and is_dark():
            set_window_dark_mode(self, True, caption_color=get_surface_color())


def _h_line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("QFrame { color: palette(mid); }")
    line.setFixedHeight(1)
    return line
