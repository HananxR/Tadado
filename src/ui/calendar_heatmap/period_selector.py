"""Period selector bar — preset buttons + custom date range for dashboard & reports."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
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
    ("week", "本周"),
    ("month", "本月"),
]


def _get_period_range(period_key: str) -> tuple[date, date]:
    """Return (start_date, end_date) inclusive for a period key."""
    today = date.today()
    if period_key == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    elif period_key == "today":
        return today, today
    elif period_key == "week":
        days_since_monday = today.isoweekday() - 1
        monday = today - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        return monday, sunday
    elif period_key == "month":
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return start, end
    else:
        return today, today


class PeriodSelectorBar(QWidget):
    """Period selector with 4 preset buttons + custom date range.

    Signals:
        period_changed(date_from, date_to, label):
            Emitted when the user selects or deselects a period.
            date_from/date_to are None when deselected.
    """

    period_changed = Signal(object, object, str)  # date|None, date|None, str

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
        layout.setSpacing(4)

        # Preset buttons
        for key, label_text in _PERIODS:
            btn = QPushButton(label_text)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._on_preset_clicked(k))
            btn.setStyleSheet(self._button_style(t, active=False))
            self._preset_buttons[key] = btn
            layout.addWidget(btn)

        # Separator
        sep = QLabel("│")
        sep.setStyleSheet(f"color: {t.border_primary}; font-size: 11px;")
        sep.setFixedWidth(16)
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sep)

        # Custom date range
        cal_label = QLabel("📅")
        cal_label.setFixedWidth(20)
        layout.addWidget(cal_label)

        self._custom_from = QDateEdit()
        self._custom_from.setCalendarPopup(True)
        self._custom_from.setDisplayFormat("yyyy-MM-dd ddd")
        self._custom_from.setDate(QDateEdit().date())
        self._custom_from.setFixedWidth(130)
        self._custom_from.setFixedHeight(28)
        self._custom_from.dateChanged.connect(self._on_custom_changed)
        layout.addWidget(self._custom_from)

        dash = QLabel("~")
        dash.setFixedWidth(12)
        dash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dash)

        self._custom_to = QDateEdit()
        self._custom_to.setCalendarPopup(True)
        self._custom_to.setDisplayFormat("yyyy-MM-dd ddd")
        self._custom_to.setDate(QDateEdit().date())
        self._custom_to.setFixedWidth(130)
        self._custom_to.setFixedHeight(28)
        self._custom_to.dateChanged.connect(self._on_custom_changed)
        layout.addWidget(self._custom_to)

        layout.addStretch()

    def _button_style(self, t, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: {t.accent}; color: {t.text_on_accent}; "
                f"border: none; border-radius: 4px; padding: 2px 10px; "
                f"font-size: 11px; font-weight: bold; }}"
            )
        return (
            f"QPushButton {{ background: transparent; color: {t.text_primary}; "
            f"border: 1px solid {t.border_primary}; border-radius: 4px; "
            f"padding: 2px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {t.accent}20; }}"
        )

    def _on_preset_clicked(self, key: str) -> None:
        btn = self._preset_buttons[key]
        t = get_tokens()

        if self._active_period == key:
            # Deselect
            btn.setChecked(False)
            btn.setStyleSheet(self._button_style(t, active=False))
            self._active_period = None
            self._sync_date_widgets(date.today(), date.today())
            self.period_changed.emit(None, None, "")
            return

        # Select this preset, deselect others
        for k, b in self._preset_buttons.items():
            if k == key:
                b.setChecked(True)
                b.setStyleSheet(self._button_style(t, active=True))
            else:
                b.setChecked(False)
                b.setStyleSheet(self._button_style(t, active=False))
        self._active_period = key
        d_from, d_to = _get_period_range(key)
        # Sync date widgets to show the preset range
        self._sync_date_widgets(d_from, d_to)
        label_map = {"yesterday": "昨天", "today": "今天", "week": "本周", "month": "本月"}
        self.period_changed.emit(d_from, d_to, label_map[key])

    def _on_custom_changed(self) -> None:
        if self._active_period is not None:
            # Deselect preset buttons
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
        """Update custom date widgets to match a range, without triggering signals."""
        self._custom_from.blockSignals(True)
        self._custom_to.blockSignals(True)
        from_qdate = type(self._custom_from.date())
        self._custom_from.setDate(from_qdate(d_from.year, d_from.month, d_from.day))
        self._custom_to.setDate(from_qdate(d_to.year, d_to.month, d_to.day))
        self._custom_from.blockSignals(False)
        self._custom_to.blockSignals(False)

    def set_custom_range(self, d_from: date, d_to: date) -> None:
        """Programmatically set a custom date range."""
        t = get_tokens()
        for b in self._preset_buttons.values():
            b.setChecked(False)
            b.setStyleSheet(self._button_style(t, active=False))
        self._active_period = None
        self._sync_date_widgets(d_from, d_to)
        self.period_changed.emit(d_from, d_to, "自定义")

    def clear_selection(self) -> None:
        """Clear all selections (preset + custom)."""
        t = get_tokens()
        for b in self._preset_buttons.values():
            b.setChecked(False)
            b.setStyleSheet(self._button_style(t, active=False))
        self._active_period = None
        self._sync_date_widgets(date.today(), date.today())

    def activate_preset(self, key: str) -> None:
        """Programmatically activate a preset button."""
        if key not in self._preset_buttons:
            return
        self._on_preset_clicked(key)
