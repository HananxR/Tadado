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

        # All 6 options, flat / tiled
        self._rb_today = QRadioButton("今天")
        self._rb_tomorrow = QRadioButton("明天 (+1天)")
        self._rb_weekend = QRadioButton("本周日")
        self._rb_week_later = QRadioButton("一周后 (+7天)")
        self._rb_month_end = QRadioButton("本月末")
        self._rb_month_later = QRadioButton("下月今天 (+1个月)")

        for rb in (self._rb_today, self._rb_tomorrow, self._rb_weekend,
                    self._rb_week_later, self._rb_month_end, self._rb_month_later):
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

        # Default: select "今天"
        self._rb_today.setChecked(True)

    def _calc(self) -> tuple:
        today = date.today()

        if self._rb_today.isChecked():
            return QDate(today), QTime(23, 59, 59), "今天"
        elif self._rb_tomorrow.isChecked():
            d = today + timedelta(days=1)
            return QDate(d), QTime(23, 59, 59), "明天"
        elif self._rb_weekend.isChecked():
            d = today + timedelta(days=(7 - today.isoweekday()))
            return QDate(d), QTime(23, 59, 59), "本周日"
        elif self._rb_week_later.isChecked():
            d = today + timedelta(days=7)
            return QDate(d), QTime(23, 59, 59), "一周后"
        elif self._rb_month_end.isChecked():
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
        else:  # _rb_month_later
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
            f"{desc} ({d.toString('yyyy-MM-dd')} {t.toString('HH:mm')})"
        )
        self.deadline_suggested.emit(d, t)
