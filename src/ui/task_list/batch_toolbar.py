"""Batch toolbar — multi-select operations above the task table."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolTip,
    QWidget,
)

from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens

BTN_STYLE = "QPushButton { font-size: 10px; padding: 2px 6px; }"


def _warn_if_empty(ids: list[str], btn: QPushButton) -> bool:
    if not ids:
        QToolTip.showText(btn.mapToGlobal(btn.rect().center()), "请先勾选要操作的任务", btn, btn.rect(), 2000)
        return True
    return False


class BatchToolbar(QWidget):
    """Toolbar for batch operations on checked tasks. Always visible."""

    batch_status_change = Signal(list, TaskStatus)
    batch_urgency_change = Signal(list, int)  # task_ids, urgency_level
    batch_delete = Signal(list)
    batch_suspend = Signal(list)
    batch_restart = Signal(list)
    batch_postpone = Signal(list, int)  # task_ids, postpone_days
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

        self._status_btn = QPushButton("更改状态")
        self._status_btn.setStyleSheet(BTN_STYLE)
        self._status_menu = QMenu(self)
        for s, label in [(TaskStatus.DOING, "进行中"), (TaskStatus.DONE, "已完成")]:
            self._status_menu.addAction(label, lambda s=s: self._emit_status(s))
        self._status_btn.setMenu(self._status_menu)
        layout.addWidget(self._status_btn)

        # Change priority dropdown
        self._urgency_btn = QPushButton("更改优先级")
        self._urgency_btn.setStyleSheet(BTN_STYLE)
        self._urgency_menu = QMenu(self)
        for value, label in [(0, "● 紧急"), (1, "● 重要"), (2, "● 关注"), (3, "● 普通")]:
            self._urgency_menu.addAction(label, lambda v=value: self._emit_urgency(v))
        self._urgency_btn.setMenu(self._urgency_menu)
        layout.addWidget(self._urgency_btn)

        self._delete_btn = QPushButton("删除")
        self._delete_btn.setStyleSheet(BTN_STYLE)
        self._delete_btn.setMinimumWidth(52)
        self._delete_btn.clicked.connect(lambda: self._emit_delete())
        layout.addWidget(self._delete_btn)

        self._suspend_btn = QPushButton("中止")
        self._suspend_btn.setStyleSheet(BTN_STYLE)
        self._suspend_btn.setMinimumWidth(52)
        self._suspend_btn.clicked.connect(lambda: self._emit_suspend())
        layout.addWidget(self._suspend_btn)

        self._restart_btn = QPushButton("重启")
        self._restart_btn.setStyleSheet(BTN_STYLE)
        self._restart_btn.setMinimumWidth(52)
        self._restart_btn.clicked.connect(lambda: self._emit_restart())
        layout.addWidget(self._restart_btn)

        self._postpone_btn = QPushButton("延后处理")
        self._postpone_btn.setStyleSheet(BTN_STYLE)
        self._postpone_menu = QMenu(self)
        for days in [1, 2, 5, 7, 10]:
            label = f"+{days}天"
            self._postpone_menu.addAction(label, lambda d=days: self._emit_postpone(d))
        self._postpone_btn.setMenu(self._postpone_menu)
        layout.addWidget(self._postpone_btn)

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

    def _emit_status(self, status: TaskStatus) -> None:
        if _warn_if_empty(self._selected_ids, self._status_btn):
            return
        self.batch_status_change.emit(list(self._selected_ids), status)

    def _emit_urgency(self, urgency: int) -> None:
        if _warn_if_empty(self._selected_ids, self._urgency_btn):
            return
        self.batch_urgency_change.emit(list(self._selected_ids), urgency)

    def _emit_delete(self) -> None:
        if _warn_if_empty(self._selected_ids, self._delete_btn):
            return
        self.batch_delete.emit(list(self._selected_ids))

    def _emit_suspend(self) -> None:
        if _warn_if_empty(self._selected_ids, self._suspend_btn):
            return
        self.batch_suspend.emit(list(self._selected_ids))

    def _emit_restart(self) -> None:
        if _warn_if_empty(self._selected_ids, self._restart_btn):
            return
        self.batch_restart.emit(list(self._selected_ids))

    def _emit_postpone(self, days: int) -> None:
        if _warn_if_empty(self._selected_ids, self._postpone_btn):
            return
        self.batch_postpone.emit(list(self._selected_ids), days)
