"""About dialog with feature overview and credits."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
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
    ("📝 任务管理", "Markdown 语法创建，状态流转（待办/进行中/已完成/已逾期），全文搜索"),
    ("📊 活动分析", "日历热力图，活动统计，标签云浏览"),
    ("🔧 批量操作", "状态变更、挂起、延后处理，Markdown / Excel 导出"),
    ("🏷 标签管理", "重命名、合并、搜索，全局自动同步"),
    ("🔒 分区管理", "多分区隔离，密码保护，自动锁定"),
    ("⏰ 智能提醒", "到期通知，免打扰，循环任务"),
    ("🎨 双主题", "亮色 / 暗色，一键跟随系统"),
]


class AboutDialog(QDialog):
    """App information and feature overview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 DeskTodoSeq")
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
        name = QLabel("DeskTodoSeq")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(name)

        version = QLabel("v1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        desc = QLabel(
            "基于 Markdown 的 Windows 桌面任务管理工具\n开源、离线、高效的个人任务管理"
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
            '<a href="https://github.com/HananxR/DeskTodoSeq"'
            ' style="color: palette(link);">'
            "github.com/HananxR/DeskTodoSeq</a>"
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
