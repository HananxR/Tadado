"""Batch toolbar — select-all, export, and selection count above the task table."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)

BTN_STYLE = "QPushButton { font-size: 10px; padding: 2px 6px; }"


class BatchToolbar(QWidget):
    """Toolbar: select-all toggle + export dropdown + selection count."""

    select_all_requested = Signal()
    deselect_all_requested = Signal()
    export_requested = Signal(str)  # "md" or "xlsx"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_ids: list[str] = []
        self._all_selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        self._toggle_select_btn = QPushButton("全选")
        self._toggle_select_btn.setStyleSheet(BTN_STYLE)
        self._toggle_select_btn.setMinimumWidth(64)
        self._toggle_select_btn.clicked.connect(self._on_toggle_select)
        layout.addWidget(self._toggle_select_btn)

        # Export dropdown
        self._export_btn = QPushButton("导出")
        self._export_btn.setStyleSheet(BTN_STYLE)
        self._export_btn.setMinimumWidth(52)
        self._export_menu = QMenu(self)
        self._export_menu.addAction("导出 MD", lambda: self.export_requested.emit("md"))
        self._export_menu.addAction("导出 Excel", lambda: self.export_requested.emit("xlsx"))
        self._export_btn.setMenu(self._export_menu)
        layout.addWidget(self._export_btn)

        self._count_label = QLabel("已选 0 项")
        self._count_label.setObjectName("batchCountLabel")
        self._count_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._count_label)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Toggle select-all / deselect-all
    # ------------------------------------------------------------------

    def _on_toggle_select(self) -> None:
        if self._all_selected:
            self.deselect_all_requested.emit()
            self._toggle_select_btn.setText("全选")
            self._all_selected = False
        else:
            self.select_all_requested.emit()
            self._toggle_select_btn.setText("取消全选")
            self._all_selected = True

    def reset_toggle(self) -> None:
        """Reset toggle button to unselected state (called externally)."""
        self._all_selected = False
        self._toggle_select_btn.setText("全选")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_selected(self, task_ids: list[str]) -> None:
        self._selected_ids = list(task_ids)
        self._count_label.setText(f"已选 {len(task_ids)} 项")
