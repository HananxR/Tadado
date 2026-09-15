"""SegmentedControl —— 分段切换控件（对齐原型 ``.seg``）。

一组互斥按钮，选中项以「抬升底色 + accent 文字」表示，用于页面内的小范围
切换（如时间轴粒度：本周 / 本月 / 近 30 天）。原型样式::

    .seg{display:flex;background:var(--bg-2);border:1px solid var(--border);
         border-radius:8px;padding:2px;gap:2px}
    .seg button.on{background:var(--surface-2);color:var(--accent);font-weight:500}
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ...utils.design_tokens import get_tokens

__all__ = ["SegmentedControl"]


class SegmentedControl(QWidget):
    """互斥分段控件。

    Signals:
        changed(value): 选中项对应的 ``itemData``。
    """

    changed = Signal(object)

    def __init__(self, items=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._items: list[tuple[object, QPushButton]] = []

        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)

        for label, value in items or ():
            self.add_item(label, value)

        self._group.idClicked.connect(self._on_id_clicked)
        self._restyle()

        from ...utils.theme_registry import register_theme_aware

        register_theme_aware(self)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def add_item(self, label: str, value) -> QPushButton:
        """追加一个分段，返回其按钮（首个自动选中）。"""
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        idx = len(self._items)
        self._group.addButton(btn, idx)
        self.layout().addWidget(btn)
        self._items.append((value, btn))
        if idx == 0:
            btn.setChecked(True)
        self._restyle()
        return btn

    def current_value(self):
        """当前选中项的值；无选中返回 ``None``。"""
        for idx, (_value, btn) in enumerate(self._items):
            if self._group.id(btn) == self._group.checkedId():
                return self._items[idx][0]
        return None

    def set_current_value(self, value) -> None:
        """按值选中（不触发 ``changed``）。"""
        for item_value, btn in self._items:
            if item_value == value:
                btn.setChecked(True)
                return

    def refresh_theme(self) -> None:
        self._restyle()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_id_clicked(self, idx: int) -> None:
        if 0 <= idx < len(self._items):
            self._restyle()
            self.changed.emit(self._items[idx][0])

    def _restyle(self) -> None:
        t = get_tokens()
        self.setStyleSheet(
            f"QWidget#segmented {{"
            f" background: {t.bg_secondary};"
            f" border: 1px solid {t.border_primary};"
            f" border-radius: 8px; }}"
            f"QWidget#segmented QPushButton {{"
            f" border: 0; background: transparent; border-radius: 6px;"
            f" padding: 4px 12px; font-size: 12px;"
            f" color: {t.text_secondary}; }}"
            f"QWidget#segmented QPushButton:hover {{ color: {t.accent}; }}"
            f"QWidget#segmented QPushButton:checked {{"
            f" background: {t.surface_raised}; color: {t.accent};"
            f" font-weight: 500; }}"
        )
