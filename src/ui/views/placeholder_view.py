"""开发中占位页 — 注册表中尚未实现的页面入口。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ...utils.design_tokens import get_tokens


class PlaceholderView(QWidget):
    """Simple "under construction" page shown before the real view lands."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = get_tokens()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        badge = QLabel(title)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {t.text_primary};")

        hint = QLabel("开发中 — 将在后续迭代上线")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {t.text_secondary}; font-size: 13px;")

        layout.addWidget(badge)
        layout.addWidget(hint)
