"""PartitionSelector — 侧栏底部的分区切换入口（图标按钮 + 弹出层）。

对齐原型 ``.part-wrap`` / ``.part-pop``：

.. code-block:: css

    .part-wrap { position: relative; }
    .part-pop  { position: absolute; left: 52px; bottom: -4px;
                 width: 184px; }
    .part-item.on { color: var(--accent); background: var(--accent-soft); }

分区入口常驻**侧栏底部、设置齿轮之上**——原型根本没有底部状态栏，把分区
下拉放在状态栏里是 1.0 时代的遗留，也是「界面混杂」的主要来源。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..utils.design_tokens import get_tokens
from ..utils.icon_loader import load_icon

POPUP_WIDTH = 184
ROW_HEIGHT = 30
TRIGGER_SIZE = 42


def _rgba(hex_color: str, alpha: float) -> str:
    """``"#4d57c3"`` + 0.16 → ``"rgba(77,87,195,0.16)"`` (原型 ``--accent-soft``)。"""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


class _PartitionRow(QPushButton):
    """One entry of the popup: name on the left, task count on the right."""

    def __init__(self, entry: dict, active: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = get_tokens()
        self.setObjectName("partitionRow")
        self.setFixedHeight(ROW_HEIGHT)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        name = QLabel(f"{entry['name']}")
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        count = QLabel(str(entry.get("count", 0)))
        count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        color = t.accent if active else t.text_primary
        name.setStyleSheet(
            f"color: {color}; font-size: 12px;"
            + (" font-weight: bold;" if active else "")
        )
        count.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")

        row = QHBoxLayout(self)
        row.setContentsMargins(9, 0, 9, 0)
        row.setSpacing(6)
        if entry.get("locked"):
            lock = QLabel("🔒")
            lock.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lock.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
            row.addWidget(lock)
        row.addWidget(name, 1)
        row.addWidget(count)

        base = _rgba(t.accent, 0.16) if active else "transparent"
        self.setStyleSheet(
            "QPushButton#partitionRow { border: none; border-radius: 6px;"
            f" background: {base}; }}"
            f"QPushButton#partitionRow:hover {{ background: {t.bg_tertiary}; }}"
        )


class _PartitionPopup(QFrame):
    """Floating partition list (原型 ``.part-pop``)。"""

    chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("partitionPopup")
        self.setFixedWidth(POPUP_WIDTH)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(6, 6, 6, 6)
        self._root.setSpacing(2)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        t = get_tokens()
        self.setStyleSheet(
            f"QFrame#partitionPopup {{ background: {t.surface_raised};"
            f" border: 1px solid {t.border_primary}; border-radius: 10px; }}"
        )

    def set_entries(self, entries: list[dict], active_id: str) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not entries:
            empty = QLabel("暂无分区")
            empty.setStyleSheet(
                f"color: {get_tokens().text_secondary}; font-size: 12px; padding: 6px 9px;"
            )
            self._root.addWidget(empty)
        else:
            for entry in entries:
                row = _PartitionRow(entry, entry["id"] == active_id)
                row.clicked.connect(lambda _checked=False, pid=entry["id"]: self._choose(pid))
                self._root.addWidget(row)

        self.adjustSize()

    def _choose(self, pid: str) -> None:
        self.hide()
        self.chosen.emit(pid)


class PartitionSelector(QWidget):
    """Rail-bottom partition switcher.

    Signals:
        partition_chosen(pid): the user picked a partition from the popup.
    """

    partition_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[dict] = []
        self._active_id: str = ""

        self._popup = _PartitionPopup()
        self._popup.chosen.connect(self.partition_chosen)

        self._btn = QPushButton()
        self._btn.setProperty("navPage", True)
        self._btn.setIcon(load_icon("folder"))
        self._btn.setIconSize(QSize(19, 19))
        self._btn.setFixedSize(TRIGGER_SIZE, TRIGGER_SIZE)
        self._btn.setFlat(True)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setToolTip("切换分区")
        self._btn.clicked.connect(self._show_popup)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._btn, 0, Qt.AlignmentFlag.AlignHCenter)

    # ------------------------------------------------------------------
    # Public API (used by PartitionController)
    # ------------------------------------------------------------------

    def set_entries(self, entries: list[dict], active_id: str) -> None:
        """Replace the popup contents.

        ``entries`` items are ``{"id", "name", "count", "locked"}``.
        """
        self._entries = list(entries)
        self._active_id = active_id or ""
        self._popup.set_entries(self._entries, self._active_id)

        entry = next((e for e in entries if e["id"] == active_id), None)
        if entry is None:
            self.set_active_name("", False)
        else:
            self.set_active_name(entry["name"], bool(entry.get("locked")))

    def set_active_name(self, name: str, locked: bool = False) -> None:
        """Update the trigger tooltip (原型 ``title="分区：工作"``）。"""
        prefix = "🔒 " if locked else ""
        self._btn.setToolTip(f"分区：{prefix}{name}" if name else "切换分区")

    def refresh_theme(self) -> None:
        """Re-apply popup styling (rows rebuild so they pick up the new tokens)."""
        self._popup.refresh_theme()
        self._popup.set_entries(self._entries, self._active_id)

    def hide_popup(self) -> None:
        self._popup.hide()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _show_popup(self) -> None:
        self._popup.set_entries(self._entries, self._active_id)
        # 原型 left:52px / bottom 对齐 → 贴按钮右侧、底边对齐
        anchor = self._btn.mapToGlobal(
            QPoint(self._btn.width() + 8, self._btn.height() - self._popup.height())
        )
        self._popup.move(anchor)
        self._popup.show()
