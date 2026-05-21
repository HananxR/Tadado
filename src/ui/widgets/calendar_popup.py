"""Custom calendar popup — strictly modelled after Obsidian Calendar's design.

Replaces QCalendarWidget's popup.  No grid lines, flat layout, accent
ring for today, filled accent circle for the selected date.
"""

from __future__ import annotations

import calendar
from datetime import date

from PySide6.QtCore import QDate, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...utils.design_tokens import get_tokens

_WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"]
_CELL = 30  # day cell size (w × h)


class _DayCell(QWidget):
    """One clickable day in the grid."""

    clicked = Signal(int, int, int)

    def __init__(
        self,
        y: int, m: int, d: int,
        is_today: bool = False,
        is_selected: bool = False,
        in_range: int = 0,  # 0=none, 1=active, 2=overdue, 3=done
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._y = y
        self._m = m
        self._d = d
        self._today = is_today
        self._selected = is_selected
        self._range = in_range  # range highlight type
        self._hovered = False
        self.setFixedSize(_CELL, _CELL)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self._y, self._m, self._d)

    def paintEvent(self, event: QPaintEvent) -> None:
        t = get_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = (_CELL - 4) / 2

        # ── range background ──
        if self._range and not self._selected:
            bg_colors = {
                1: QColor(t.accent),        # active range
                2: QColor(t.danger),        # overdue
                3: QColor(t.success),       # done
            }
            if self._range in bg_colors:
                c = bg_colors[self._range]
                c.setAlpha(30)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRect(1, 1, w - 2, h - 2), 6, 6)

        # ── hover background ──
        if self._hovered and not self._selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.bg_tertiary))
            p.drawRoundedRect(QRect(1, 1, w - 2, h - 2), 6, 6)

        # ── selected: filled accent circle ──
        if self._selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(QColor(t.text_on_accent))
        # ── today: accent outline ring ──
        elif self._today:
            p.setPen(QPen(QColor(t.accent), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(QColor(t.accent))
        else:
            p.setPen(QColor(t.text_primary))

        font = QFont()
        font.setPointSize(11)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._d))
        p.end()


class CalendarPopup(QDialog):
    """Popup calendar that looks like Obsidian's Calendar plugin.

    Usage::

        popup = CalendarPopup(current_date, parent)
        popup.date_selected.connect(callback)
        # Position with smart_place() then popup.exec()
    """

    date_selected = Signal(QDate)

    def __init__(
        self,
        initial: date | QDate | None = None,
        parent: QWidget | None = None,
        range_from: date | None = None,
        range_to: date | None = None,
        range_kind: str = "",  # "" | "overdue" | "done"
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setObjectName("calendarPopup")

        if isinstance(initial, QDate):
            initial = date(initial.year(), initial.month(), initial.day())
        self._viewing = initial or date.today()
        self._selected = initial
        self._range_from = range_from
        self._range_to = range_to
        self._range_kind = range_kind

        self._build_ui()
        self._refresh()

    # ── UI construction ──────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(2)

        # ── Navigation: ‹  title  › ──────────────────────────────
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(0)

        self._prev_btn = QLabel("‹")
        self._prev_btn.setObjectName("calNavBtn")
        self._prev_btn.setFixedSize(28, 28)
        self._prev_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.mousePressEvent = lambda e: self._prev_month()
        nav.addWidget(self._prev_btn)

        self._title_btn = QLabel()
        self._title_btn.setObjectName("calTitleBtn")
        self._title_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_btn.mousePressEvent = lambda e: self._go_today()
        nav.addWidget(self._title_btn, 1)

        self._next_btn = QLabel("›")
        self._next_btn.setObjectName("calNavBtn")
        self._next_btn.setFixedSize(28, 28)
        self._next_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.mousePressEvent = lambda e: self._next_month()
        nav.addWidget(self._next_btn)

        root.addLayout(nav)

        # ── Weekday header ───────────────────────────────────────
        wk = QHBoxLayout()
        wk.setContentsMargins(0, 0, 0, 0)
        wk.setSpacing(0)
        for name in _WEEKDAYS:
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(_CELL, 20)
            lbl.setObjectName("calWeekday")
            wk.addWidget(lbl)
        root.addLayout(wk)

        # ── Day grid placeholder ─────────────────────────────────
        self._grid_widget = QWidget()
        self._grid = QVBoxLayout(self._grid_widget)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(0)
        root.addWidget(self._grid_widget)

    # ── Refresh ──────────────────────────────────────────────────────
    def _refresh(self) -> None:
        t = get_tokens()
        y, m = self._viewing.year, self._viewing.month
        today = date.today()

        self._title_btn.setText(f"{y}年{m}月")

        # Clear old grid
        self._clear_grid()

        cal = calendar.Calendar(firstweekday=6)
        weeks = cal.monthdayscalendar(y, m)

        for week in weeks:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            for d in week:
                if d == 0:
                    # Empty slot — just spacing
                    spacer = QWidget()
                    spacer.setFixedSize(_CELL, _CELL)
                    row.addWidget(spacer)
                else:
                    is_today = (y, m, d) == (today.year, today.month, today.day)
                    is_sel = (
                        self._selected is not None
                        and (y, m, d) == (self._selected.year, self._selected.month, self._selected.day)
                    )
                    cell_date = date(y, m, d)
                    in_range = self._range_for(cell_date)
                    cell = _DayCell(y, m, d, is_today, is_sel, in_range, self)
                    cell.clicked.connect(self._on_day)
                    row.addWidget(cell)
            self._grid.addLayout(row)

        self.adjustSize()

    def _range_for(self, d: date) -> int:
        """Return range highlight type for *d*: 0=none, 1=active, 2=overdue, 3=done."""
        if self._range_kind == "done":
            if self._range_from and self._range_to and self._range_from <= d <= self._range_to:
                return 3
            return 0
        if self._range_from and self._range_to:
            if self._range_from <= d <= self._range_to:
                return 1  # active range
            if self._range_kind == "overdue" and d > self._range_to:
                return 2  # overdue
        return 0

    def _clear_grid(self) -> None:
        grid = self._grid
        while grid.count():
            item = grid.takeAt(0)
            if item.layout():
                sub = item.layout()
                while sub.count():
                    si = sub.takeAt(0)
                    if si.widget():
                        si.widget().deleteLater()
                sub.deleteLater()

    # ── Actions ──────────────────────────────────────────────────────
    def _on_day(self, y: int, m: int, d: int) -> None:
        self._selected = date(y, m, d)
        self.date_selected.emit(QDate(y, m, d))
        self.accept()

    def _prev_month(self) -> None:
        y, m = self._viewing.year, self._viewing.month
        if m == 1:
            self._viewing = date(y - 1, 12, 1)
        else:
            self._viewing = date(y, m - 1, 1)
        self._refresh()

    def _next_month(self) -> None:
        y, m = self._viewing.year, self._viewing.month
        if m == 12:
            self._viewing = date(y + 1, 1, 1)
        else:
            self._viewing = date(y, m + 1, 1)
        self._refresh()

    def _go_today(self) -> None:
        self._viewing = date.today()
        self._refresh()

    # ── Public helpers ───────────────────────────────────────────────
    def set_date(self, d: date | QDate) -> None:
        if isinstance(d, QDate):
            d = date(d.year(), d.month(), d.day())
        self._selected = d
        self._viewing = d

    def smart_place(self, anchor: QWidget) -> None:
        """Position the popup near *anchor* without overflowing the screen.

        Tries below, then above.  Shifts horizontally if the right edge
        would be clipped.
        """
        self.adjustSize()  # ensure sizeHint is up-to-date
        ph = self.sizeHint().height()
        pw = self.sizeHint().width()

        screen = anchor.screen()
        if screen is None:
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        # Anchor bottom-left in global coords
        anchor_global = anchor.mapToGlobal(QPoint(0, anchor.height()))

        # Vertical: prefer below, fallback above
        if anchor_global.y() + ph <= avail.bottom():
            y = anchor_global.y()
        else:
            y = anchor.mapToGlobal(QPoint(0, 0)).y() - ph

        # Horizontal: prefer aligned-left, shift if right edge overflows
        x = anchor_global.x()
        if x + pw > avail.right():
            x = avail.right() - pw
        if x < avail.left():
            x = avail.left()

        self.move(x, y)
