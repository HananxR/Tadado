"""About dialog with app info and reference sources."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class AboutDialog(QDialog):
    """App information and credits."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 DeskTodoSeq")
        self.setObjectName("aboutDialog")
        self.setFixedSize(420, 360)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 20, 24, 20)

        name = QLabel("DeskTodoSeq")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(name)

        version = QLabel("v0.1.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #888;")
        layout.addWidget(version)

        desc = QLabel("基于 Markdown 的 Windows 桌面任务管理工具")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(8)

        refs = QLabel(
            "<b>参考来源：</b><br><br>"
            "&bull; <b>Todoseq</b> — Markdown 任务序列化规范<br>"
            "&bull; <b>Org-mode</b> — Emacs 任务管理与状态流转<br>"
            "&bull; <b>GitHub Contribution Graph</b> — 日历热力图设计<br>"
            "&bull; <b>Qt Framework</b> — 跨平台 GUI 框架<br>"
            "&bull; <b>SQLite FTS5</b> — 全文搜索引擎"
        )
        refs.setWordWrap(True)
        layout.addWidget(refs)

        layout.addSpacing(8)

        license_label = QLabel("MIT License")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label.setStyleSheet("color: #888;")
        layout.addWidget(license_label)

        author = QLabel("作者: Hanxy")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author)

        layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
