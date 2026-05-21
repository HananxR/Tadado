"""Custom time picker popup — hour / minute columns with click selection.

Merges display and interaction into one component:
- A QLineEdit for manual HH:mm input
- Clicking it opens a popup with hour (00–23) and minute (00–59) columns
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTime, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIntValidator,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...utils.design_tokens import get_tokens


class _TimeCell(QWidget):
    """One clickable hour or minute cell."""

    clicked = Signal(int)

    def __init__(self, value: int, selected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = value
        self._selected = selected
        self._hovered = False
        self.setFixedSize(48, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self._value)

    def paintEvent(self, event: QPaintEvent) -> None:
        t = get_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        if self._selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRect(2, 2, w - 4, h - 4), 6, 6)
            p.setPen(QColor(t.text_on_accent))
        elif self._hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.bg_tertiary))
            p.drawRoundedRect(QRect(2, 2, w - 4, h - 4), 6, 6)
            p.setPen(QColor(t.text_primary))
        else:
            p.setPen(QColor(t.text_primary))

        font = QFont()
        font.setPixelSize(12)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._value:02d}")
        p.end()


class TimePopup(QDialog):
    """Popup time picker with hour / minute columns.

    Usage::

        popup = TimePopup(current_time, parent)
        popup.time_selected.connect(callback)
        popup.smart_place(anchor_widget)
        popup.exec()
    """

    time_selected = Signal(QTime)

    def __init__(
        self,
        initial: QTime | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setObjectName("timePopup")

        self._hour = initial.hour() if initial else 0
        self._minute = initial.minute() if initial else 0

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # Header
        title = QLabel("选择时间")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("timePopupTitle")
        root.addWidget(title)

        # Hour / Minute columns
        cols = QHBoxLayout()
        cols.setSpacing(4)

        # Hour column
        hour_box = QVBoxLayout()
        hour_box.setSpacing(0)
        hour_label = QLabel("时")
        hour_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hour_label.setObjectName("timeColLabel")
        hour_box.addWidget(hour_label)

        hour_scroll = QScrollArea()
        hour_scroll.setObjectName("timeColScroll")
        hour_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hour_scroll.setWidgetResizable(True)
        t = get_tokens()
        hour_scroll.setStyleSheet(
            f"QScrollArea#timeColScroll {{ background-color: {t.bg_secondary}; }}"
            f"QScrollArea#timeColScroll QWidget {{ background-color: {t.bg_secondary}; }}"
        )
        self._hour_widget = QWidget()
        self._hour_layout = QVBoxLayout(self._hour_widget)
        self._hour_layout.setContentsMargins(0, 0, 0, 0)
        self._hour_layout.setSpacing(0)
        for h in range(24):
            cell = _TimeCell(h, h == self._hour, self)
            cell.clicked.connect(self._on_hour)
            self._hour_layout.addWidget(cell)
        hour_scroll.setWidget(self._hour_widget)
        hour_scroll.setFixedHeight(200)
        hour_box.addWidget(hour_scroll)
        cols.addLayout(hour_box)

        # Minute column
        min_box = QVBoxLayout()
        min_box.setSpacing(0)
        min_label = QLabel("分")
        min_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        min_label.setObjectName("timeColLabel")
        min_box.addWidget(min_label)

        min_scroll = QScrollArea()
        min_scroll.setObjectName("timeColScroll")
        min_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        min_scroll.setWidgetResizable(True)
        min_scroll.setStyleSheet(
            f"QScrollArea#timeColScroll {{ background-color: {t.bg_secondary}; }}"
            f"QScrollArea#timeColScroll QWidget {{ background-color: {t.bg_secondary}; }}"
        )
        self._min_widget = QWidget()
        self._min_layout = QVBoxLayout(self._min_widget)
        self._min_layout.setContentsMargins(0, 0, 0, 0)
        self._min_layout.setSpacing(0)
        for m in range(60):
            cell = _TimeCell(m, m == self._minute, self)
            cell.clicked.connect(self._on_minute)
            self._min_layout.addWidget(cell)
        min_scroll.setWidget(self._min_widget)
        min_scroll.setFixedHeight(200)
        min_box.addWidget(min_scroll)
        cols.addLayout(min_box)

        root.addLayout(cols)

        self.adjustSize()

        # Scroll to show current selection
        self._hour_widget.setFixedHeight(24 * 32)
        self._min_widget.setFixedHeight(60 * 32)
        hour_scroll.verticalScrollBar().setValue(self._hour * 32 - 80)
        min_scroll.verticalScrollBar().setValue(self._minute * 32 - 80)

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_hour(self, h: int) -> None:
        self._hour = h
        self.time_selected.emit(QTime(self._hour, self._minute))
        self.accept()

    def _on_minute(self, m: int) -> None:
        self._minute = m
        self.time_selected.emit(QTime(self._hour, self._minute))
        self.accept()

    # ── Positioning ───────────────────────────────────────────────────
    def smart_place(self, anchor: QWidget) -> None:
        """Position near *anchor* without overflowing the screen."""
        self.adjustSize()
        ph = self.sizeHint().height()
        pw = self.sizeHint().width()

        screen = anchor.screen()
        if screen is None:
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()

        anchor_global = anchor.mapToGlobal(QPoint(0, anchor.height()))
        if anchor_global.y() + ph <= avail.bottom():
            y = anchor_global.y()
        else:
            y = anchor.mapToGlobal(QPoint(0, 0)).y() - ph
        x = anchor_global.x()
        if x + pw > avail.right():
            x = avail.right() - pw
        if x < avail.left():
            x = avail.left()
        self.move(x, y)


# ── Combined widget: display + popup in one ────────────────────────────────


class TimeEdit(QWidget):
    """A time editor that merges manual input and picker popup.

    Looks like a QLineEdit showing ``HH:mm``.  Clicking it opens
    :class:`TimePopup`; manual typing is validated (00–23 : 00–59).
    """

    time_changed = Signal(QTime)

    def __init__(
        self, initial: QTime | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        t = initial or QTime(23, 59)
        self._time = t

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._edit = QLineEdit()
        self._edit.setObjectName("timeEdit")
        self._edit.setText(t.toString("HH:mm"))
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setFixedWidth(56)
        self._edit.setMaxLength(5)
        self._edit.setToolTip("输入时间 (HH:mm) 或点击选择")
        self._edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit.installEventFilter(self)
        self._edit.editingFinished.connect(self._on_editing_finished)
        layout.addWidget(self._edit)

    # -- value access ----------------------------------------------------
    def time(self) -> QTime:
        return self._time

    def setTime(self, t: QTime) -> None:
        self._time = t
        self._edit.blockSignals(True)
        self._edit.setText(t.toString("HH:mm"))
        self._edit.blockSignals(False)

    # -- internals -------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        if obj is self._edit and event.type() == QEvent.Type.MouseButtonPress:
            self._show_popup()
            return True
        return super().eventFilter(obj, event)

    def _show_popup(self) -> None:
        popup = TimePopup(self._time, self)
        popup.time_selected.connect(self._on_time_selected)
        popup.smart_place(self._edit)
        popup.exec()

    def _on_time_selected(self, t: QTime) -> None:
        self._time = t
        self._edit.blockSignals(True)
        self._edit.setText(t.toString("HH:mm"))
        self._edit.blockSignals(False)
        self.time_changed.emit(t)

    def _on_editing_finished(self) -> None:
        text = self._edit.text().strip()
        parts = text.replace("：", ":").split(":")
        try:
            h = int(parts[0]) if len(parts) >= 1 else 0
            m = int(parts[1]) if len(parts) >= 2 else 0
        except ValueError:
            h, m = self._time.hour(), self._time.minute()

        h = max(0, min(23, h))
        m = max(0, min(59, m))
        t = QTime(h, m)
        self._time = t
        self._edit.blockSignals(True)
        self._edit.setText(t.toString("HH:mm"))
        self._edit.blockSignals(False)
        if t != QTime(h, m) if False else True:  # always emit
            self.time_changed.emit(t)
