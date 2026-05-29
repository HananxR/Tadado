"""Unified dropdown widget with selection checkmark indicator."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QStyle, QStyledItemDelegate

from ...utils.design_tokens import get_tokens


class _CheckmarkDelegate(QStyledItemDelegate):
    """Draws a checkmark on the currently-selected popup item."""

    def __init__(self, combo: QComboBox, parent=None):
        super().__init__(parent)
        self._combo = combo

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)

        if index.row() != self._combo.currentIndex():
            return

        tokens = get_tokens()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if option.state & QStyle.StateFlag.State_Selected:
            pen_color = QColor(tokens.text_on_accent)
        else:
            pen_color = QColor(tokens.accent)

        painter.setPen(QPen(pen_color, 1.5))
        check_rect = QRect(
            option.rect.left() + 4,
            option.rect.top(),
            18,
            option.rect.height(),
        )
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            check_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "✓",
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        sz = super().sizeHint(option, index)
        return QSize(sz.width() + 18, sz.height())


class DropdownWidget(QComboBox):
    """Unified dropdown selector with checkmark on selected popup item.

    Drop-in replacement for ``QComboBox``. Identical API; adds a ``✓``
    checkmark to the currently-selected item in the popup list.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._delegate = _CheckmarkDelegate(self)
        self.view().setItemDelegate(self._delegate)

    def showPopup(self) -> None:
        self.view().updateGeometries()
        super().showPopup()
