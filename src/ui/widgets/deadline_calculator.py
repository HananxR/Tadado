"""Deadline interval calculator — compact QDialog popup."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from PySide6.QtCore import QDate, QTime, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...utils.design_tokens import get_tokens
from ...utils.widget_utils import combo_width
from .dropdown import DropdownWidget


class DeadlineIntervalCalculator(QDialog):
    """Popup dialog for quick deadline calculation. Auto-previews on any change."""

    deadline_suggested = Signal(QDate, QTime)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("快速计算")
        self.setMinimumWidth(300)
        self._build_ui()
        self._apply()

    def _build_ui(self) -> None:
        t = get_tokens()
        self.setStyleSheet(
            f"QDialog {{ background-color: {t.bg_secondary}; }}"
            f"QLabel {{ color: {t.text_primary}; }}"
            f"QRadioButton {{ color: {t.text_primary}; font-size: 12px; spacing: 6px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Task type dropdown
        type_row = QHBoxLayout()
        type_label = QLabel("时间粒度:")
        type_label.setStyleSheet(f"font-weight: bold; color: {t.text_primary};")
        type_row.addWidget(type_label)
        self._type_combo = DropdownWidget()
        self._type_combo.setObjectName("calcTypeCombo")
        self._type_combo.addItems(["天", "周", "月"])
        self._type_combo.setFixedWidth(combo_width(2))
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_row.addWidget(self._type_combo)
        type_row.addStretch()
        layout.addLayout(type_row)

        # Radio buttons — all added, visibility controlled
        self._rb_temp1 = QRadioButton("今天 23:59:59")
        self._rb_temp2 = QRadioButton("当前 +1 天")
        self._rb_week1 = QRadioButton("本周星期日 23:59:59")
        self._rb_week2 = QRadioButton("今天 +7 天")
        self._rb_month1 = QRadioButton("本月末 23:59:59")
        self._rb_month2 = QRadioButton("今天 +1 个自然月")

        for rb in (self._rb_temp1, self._rb_temp2, self._rb_week1, self._rb_week2,
                    self._rb_month1, self._rb_month2):
            rb.clicked.connect(self._apply)
            layout.addWidget(rb)

        # Preview
        self._preview = QLabel()
        self._preview.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {t.accent}; padding: 6px 8px;"
            f"background: {t.accent}18; border-radius: 4px;"
        )
        layout.addWidget(self._preview)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        apply_btn = QPushButton("应用")
        apply_btn.setObjectName("saveBtn")
        apply_btn.clicked.connect(lambda: (self._apply(), self.accept()))
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

        # Show initial state
        self._on_type_changed()

    def _on_type_changed(self) -> None:
        """Combo change: show/hide options and auto-check first one."""
        idx = self._type_combo.currentIndex()
        self._rb_temp1.setVisible(idx == 0)
        self._rb_temp2.setVisible(idx == 0)
        self._rb_week1.setVisible(idx == 1)
        self._rb_week2.setVisible(idx == 1)
        self._rb_month1.setVisible(idx == 2)
        self._rb_month2.setVisible(idx == 2)
        # Auto-check first visible
        for rb, vis in [(self._rb_temp1, idx == 0), (self._rb_week1, idx == 1), (self._rb_month1, idx == 2)]:
            if vis:
                rb.blockSignals(True)
                rb.setChecked(True)
                rb.blockSignals(False)
                break
        self._apply()

    def _calc(self) -> tuple:
        idx = self._type_combo.currentIndex()
        today = date.today()

        if idx == 0:  # temp
            if self._rb_temp1.isChecked():
                return QDate(today), QTime(23, 59, 59), "今天 23:59"
            d = today + timedelta(days=1)
            return QDate(d), QTime(23, 59, 59), "明天"
        elif idx == 1:  # week
            if self._rb_week1.isChecked():
                d = today + timedelta(days=(7 - today.isoweekday()))
                return QDate(d), QTime(23, 59, 59), "本周日"
            d = today + timedelta(days=7)
            return QDate(d), QTime(23, 59, 59), "今天+7天"
        else:  # month
            if self._rb_month1.isChecked():
                _, last = calendar.monthrange(today.year, today.month)
                d = today.replace(day=last)
                if d < today:
                    if today.month < 12:
                        d = date(today.year, today.month + 1, 1)
                    else:
                        d = date(today.year + 1, 1, 1)
                    _, last = calendar.monthrange(d.year, d.month)
                    d = d.replace(day=last)
                return QDate(d), QTime(23, 59, 59), "本月末"
            if today.month == 12:
                try:
                    d = date(today.year + 1, 1, today.day)
                except ValueError:
                    d = (date(today.year + 1, 2, 1) - timedelta(days=1))
            else:
                try:
                    d = today.replace(month=today.month + 1)
                except ValueError:
                    d = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            return QDate(d), QTime(23, 59, 59), "下月今天"

    def _apply(self) -> None:
        d, t, desc = self._calc()
        self._preview.setText(
            f"{d.toString('yyyy-MM-dd')} {t.toString('HH:mm')} ({desc})"
        )
        self.deadline_suggested.emit(d, t)
