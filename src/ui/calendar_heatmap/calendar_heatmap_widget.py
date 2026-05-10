"""GitHub-style calendar heatmap widget with custom painting and year navigation."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...models.repository import TaskRepository
from .heatmap_model import HeatmapModel

_CELL_SIZE = 14
_CELL_GAP = 3
_CELL_STEP = _CELL_SIZE + _CELL_GAP
_LEFT_MARGIN = 32
_TOP_MARGIN = 20
_RIGHT_MARGIN = 12
_BOTTOM_MARGIN = 8


class _HeatmapGrid(QWidget):
    """Custom-painted grid portion of the heatmap."""

    date_selected = Signal(date)
    date_hovered = Signal(object)  # date or None

    _DAY_LABELS: list[str] = ["", "一", "", "三", "", "五", ""]

    def __init__(self, model: HeatmapModel, colors: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self._colors = colors
        self._hovered_date: date | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(700, 128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def refresh(self) -> None:
        self.update()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        year = self._model.current_year()

        # Day labels
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        for row, label in enumerate(self._DAY_LABELS):
            if label:
                y = _TOP_MARGIN + row * _CELL_STEP + _CELL_SIZE
                p.setPen(QColor("#888"))
                p.drawText(QRect(0, y - 8, _LEFT_MARGIN - 4, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)

        # Month labels
        self._draw_month_labels(p, year)

        # Cells
        d = self._first_monday(year)
        for col in range(53):
            for row in range(7):
                cell_date = d + timedelta(days=col * 7 + row)
                if cell_date.year != year:
                    continue
                self._draw_cell(p, col, row, cell_date)

    def _draw_month_labels(self, p: QPainter, year: int) -> None:
        d = self._first_monday(year)
        last_label_col = -99
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(QColor("#888"))

        for col in range(53):
            cell_date = d + timedelta(days=col * 7)
            if cell_date.year != year:
                continue
            month = cell_date.month
            if col == 0 or cell_date.day <= 7:
                month_col = col
                if month_col != last_label_col + 1 and month_col != last_label_col:
                    last_label_col = month_col
                    month_names = ["", "1月", "2月", "3月", "4月", "5月", "6月",
                                   "7月", "8月", "9月", "10月", "11月", "12月"]
                    x = _LEFT_MARGIN + col * _CELL_STEP
                    p.drawText(QRect(x, 0, 40, _TOP_MARGIN), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, month_names[month])

    def _draw_cell(self, p: QPainter, col: int, row: int, cell_date: date) -> None:
        x = _LEFT_MARGIN + col * _CELL_STEP
        y = _TOP_MARGIN + row * _CELL_STEP
        rect = QRect(x, y, _CELL_SIZE, _CELL_SIZE)

        level = self._model.color_level(cell_date, self._colors)
        color_hex = self._colors.get(level, "#ebedf0")
        color = QColor(color_hex)

        # Future dates get lighter treatment
        if cell_date > date.today():
            color.setAlpha(40)
        elif level == "level_0":
            pass  # Default empty color

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(rect, 2, 2)

        # Highlight hovered cell
        if cell_date == self._hovered_date:
            p.setPen(QPen(QColor("#333"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    @staticmethod
    def _first_monday(year: int) -> date:
        jan1 = date(year, 1, 1)
        return jan1 - timedelta(days=jan1.weekday())

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        d = self._date_at_pos(event.pos())
        if d != self._hovered_date:
            self._hovered_date = d
            self.date_hovered.emit(d)
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            d = self._date_at_pos(event.pos())
            if d is not None:
                self.date_selected.emit(d)

    def leaveEvent(self, event) -> None:
        self._hovered_date = None
        self.date_hovered.emit(None)
        self.update()

    def _date_at_pos(self, pos: QPoint) -> date | None:
        col = (pos.x() - _LEFT_MARGIN + _CELL_GAP // 2) // _CELL_STEP
        row = (pos.y() - _TOP_MARGIN + _CELL_GAP // 2) // _CELL_STEP
        if col < 0 or row < 0 or col >= 53 or row >= 7:
            return None
        d = self._first_monday(self._model.current_year()) + timedelta(days=col * 7 + row)
        if d.year != self._model.current_year():
            return None
        return d

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(_LEFT_MARGIN + 53 * _CELL_STEP + _RIGHT_MARGIN, 130)

    def minimumSizeHint(self) -> QSize:
        return QSize(700, 128)


class CalendarHeatmapWidget(QWidget):
    """Complete heatmap widget: year navigation + painted grid."""

    date_selected = Signal(date)

    def __init__(
        self,
        repository: TaskRepository,
        config: AppConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("calendarHeatmap")

        self._model = HeatmapModel(repository)
        self._config = config

        self._model.load_year(self._model.current_year())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Year navigation
        nav = QHBoxLayout()
        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedWidth(28)
        self._prev_btn.clicked.connect(self._prev_year)
        self._year_label = QLabel(str(self._model.current_year()))
        self._year_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._year_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._next_btn = QPushButton(">")
        self._next_btn.setFixedWidth(28)
        self._next_btn.clicked.connect(self._next_year)

        nav.addStretch()
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._year_label)
        nav.addWidget(self._next_btn)
        nav.addStretch()
        layout.addLayout(nav)

        # Grid
        colors = self._config.heatmap_colors
        self._grid = _HeatmapGrid(self._model, colors)
        self._grid.date_selected.connect(self._on_date_selected)
        self._grid.date_hovered.connect(self._on_date_hovered)
        layout.addWidget(self._grid)

        # Hover tooltip label
        self._tooltip = QLabel()
        self._tooltip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tooltip.setStyleSheet("color: #888; font-size: 11px;")
        self._tooltip.setFixedHeight(18)
        layout.addWidget(self._tooltip)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self._model.load_year(self._model.current_year())
        self._grid.refresh()

    def set_year(self, year: int) -> None:
        self._model.load_year(year)
        self._year_label.setText(str(year))
        self._grid.refresh()

    def current_year(self) -> int:
        return self._model.current_year()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _prev_year(self) -> None:
        self.set_year(self._model.current_year() - 1)

    def _next_year(self) -> None:
        self.set_year(self._model.current_year() + 1)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_date_selected(self, d: date) -> None:
        self.date_selected.emit(d)

    def _on_date_hovered(self, d: date | None) -> None:
        if d is None:
            self._tooltip.setText("")
        else:
            count = self._model.count_for_date(d)
            if count > 0:
                self._tooltip.setText(f"{d.isoformat()} — {count} 个任务")
            else:
                self._tooltip.setText(f"{d.isoformat()} — 无任务")
