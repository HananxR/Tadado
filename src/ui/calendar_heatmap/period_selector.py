"""Period selector bar — preset buttons + custom date range for dashboard & reports."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal, QTimer, QEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ...utils.design_tokens import get_tokens

_PERIODS = [
    ("yesterday", "昨天"),
    ("today", "今天"),
    ("last_week", "上周"),
    ("week", "本周"),
    ("last_month", "上月"),
    ("month", "本月"),
]


def _get_period_range(period_key: str) -> tuple[date, date]:
    today = date.today()
    if period_key == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    elif period_key == "today":
        return today, today
    elif period_key == "last_week":
        last_monday = today - timedelta(days=today.isoweekday() + 6)
        last_sunday = last_monday + timedelta(days=6)
        return last_monday, last_sunday
    elif period_key == "week":
        days_since_monday = today.isoweekday() - 1
        monday = today - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        return monday, sunday
    elif period_key == "last_month":
        first_of_this_month = today.replace(day=1)
        last_day_of_last_month = first_of_this_month - timedelta(days=1)
        first_of_last_month = last_day_of_last_month.replace(day=1)
        return first_of_last_month, last_day_of_last_month
    elif period_key == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return start, end
    else:
        return today, today


def _make_date_edit() -> _CalendarDateEdit:
    """Create a date edit matching the task editor's style + CalendarPopup."""
    w = _CalendarDateEdit()
    w.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    w.setDisplayFormat("yyyy-MM-dd")
    w.setDate(QDate.currentDate())
    w.setMinimumDate(QDate(2000, 1, 1))
    w.setMaximumDate(QDate(2100, 12, 31))
    w.setFixedWidth(95)
    w.setFixedHeight(28)
    w.setStyleSheet("QDateEdit { font-size: 10px; padding: 0px 4px; border: none; }")
    w.setAlignment(Qt.AlignmentFlag.AlignCenter)
    w.setToolTip("点击选择日期")
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    return w


class _CalendarDateEdit(QDateEdit):
    """QDateEdit that opens CalendarPopup on click, matching task editor behavior."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.lineEdit() and event.type() == QEvent.Type.MouseButtonPress:
            from ..widgets.calendar_popup import CalendarPopup
            qd = self.date()
            cur = date(qd.year(), qd.month(), qd.day())
            popup = CalendarPopup(cur, self)
            popup.date_selected.connect(self._on_popup_date)
            popup.smart_place(self)
            popup.exec()
            return True
        return super().eventFilter(obj, event)

    def _on_popup_date(self, qd: QDate) -> None:
        self.setDate(qd)


class PeriodSelectorBar(QWidget):
    """Period selector with 4 preset buttons + custom date range.

    Signals:
        period_changed(date_from, date_to, label):
            Emitted when the user selects or deselects a period.
            date_from/date_to are None when deselected.
    """

    period_changed = Signal(object, object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_period: str | None = None
        self._preset_buttons: dict[str, QPushButton] = {}
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._emit_custom_range)
        self._build_ui()

    def _build_ui(self) -> None:
        t = get_tokens()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        for key, label_text in _PERIODS:
            btn = QPushButton(label_text)
            btn.setObjectName("periodPresetBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._on_preset_clicked(k))
            self._preset_buttons[key] = btn
            layout.addWidget(btn)

        sep = QLabel("│")
        sep.setObjectName("activitySep")
        sep.setFixedWidth(16)
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sep)

        # Custom date range with CalendarPopup
        cal_label = QLabel("📅")
        cal_label.setFixedWidth(20)
        layout.addWidget(cal_label)

        self._custom_from = _make_date_edit()
        self._custom_from.dateChanged.connect(self._on_custom_changed)
        layout.addWidget(self._custom_from)

        dash = QLabel("~")
        dash.setFixedWidth(12)
        dash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dash)

        self._custom_to = _make_date_edit()
        self._custom_to.dateChanged.connect(self._on_custom_changed)
        layout.addWidget(self._custom_to)

        layout.addStretch()

    def _button_style(self, t, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {t.accent}; color: {t.text_on_accent}; "
                f"border: none; border-radius: 4px; padding: 2px 8px; "
                f"font-size: 10px; font-weight: bold; }}"
            )
        return (
            f"QPushButton {{ background: transparent; color: {t.text_primary}; "
            f"border: 1px solid {t.border_primary}; border-radius: 4px; "
            f"padding: 2px 8px; font-size: 10px; }}"
            f"QPushButton:hover {{ background: {t.accent}20; }}"
        )

    def _on_preset_clicked(self, key: str) -> None:
        btn = self._preset_buttons[key]
        t = get_tokens()

        if self._active_period == key:
            btn.setChecked(False)
            btn.setStyleSheet(self._button_style(t, active=False))
            self._active_period = None
            self._sync_date_widgets(date.today(), date.today())
            self.period_changed.emit(None, None, "")
            return

        for k, b in self._preset_buttons.items():
            if k == key:
                b.setChecked(True)
                b.setStyleSheet(self._button_style(t, active=True))
            else:
                b.setChecked(False)
                b.setStyleSheet(self._button_style(t, active=False))
        self._active_period = key
        d_from, d_to = _get_period_range(key)
        self._sync_date_widgets(d_from, d_to)
        label_map = {"yesterday": "昨天", "today": "今天", "last_week": "上周", "week": "本周", "last_month": "上月", "month": "本月"}
        self.period_changed.emit(d_from, d_to, label_map[key])

    def _on_custom_changed(self) -> None:
        if self._active_period is not None:
            t = get_tokens()
            for b in self._preset_buttons.values():
                b.setChecked(False)
                b.setStyleSheet(self._button_style(t, active=False))
            self._active_period = None
        self._debounce_timer.start()

    def _emit_custom_range(self) -> None:
        qd_from = self._custom_from.date()
        qd_to = self._custom_to.date()
        d_from = date(qd_from.year(), qd_from.month(), qd_from.day())
        d_to = date(qd_to.year(), qd_to.month(), qd_to.day())
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        self.period_changed.emit(d_from, d_to, "自定义")

    def _sync_date_widgets(self, d_from: date, d_to: date) -> None:
        self._custom_from.blockSignals(True)
        self._custom_to.blockSignals(True)
        self._custom_from.setDate(QDate(d_from.year, d_from.month, d_from.day))
        self._custom_to.setDate(QDate(d_to.year, d_to.month, d_to.day))
        self._custom_from.blockSignals(False)
        self._custom_to.blockSignals(False)

    def set_custom_range(self, d_from: date, d_to: date) -> None:
        t = get_tokens()
        for b in self._preset_buttons.values():
            b.setChecked(False)
            b.setStyleSheet(self._button_style(t, active=False))
        self._active_period = None
        self._sync_date_widgets(d_from, d_to)
        self.period_changed.emit(d_from, d_to, "自定义")

    def clear_selection(self) -> None:
        t = get_tokens()
        for b in self._preset_buttons.values():
            b.setChecked(False)
            b.setStyleSheet(self._button_style(t, active=False))
        self._active_period = None
        self._sync_date_widgets(date.today(), date.today())

    def activate_preset(self, key: str) -> None:
        if key not in self._preset_buttons:
            return
        self._on_preset_clicked(key)
