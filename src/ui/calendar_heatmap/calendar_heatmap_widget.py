"""Calendar heatmap — month-partitioned 7×5 matrix layout with activity gradient."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
)
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
from ...utils.design_tokens import get_tokens
from ...utils.widget_utils import combo_width
from ..widgets.dropdown import DropdownWidget
from .heatmap_model import HeatmapModel
from .heatmap_tooltip import HeatmapTooltip

# ── Layout constants ──────────────────────────────────────────────────────────
_LEFT_MARGIN = 38
_TOP_MARGIN = 18
_RIGHT_MARGIN = 12
_BOTTOM_MARGIN = 4
_LEGEND_HEIGHT = 14
_MIN_CELL = 10
_TARGET_CELL = 12
_MONTH_GAP = 3
_WEEKS_PER_MONTH = 5
_DAYS_PER_WEEK = 7
_MONTHS_PER_YEAR = 12
_TOTAL_COLS = _MONTHS_PER_YEAR * _WEEKS_PER_MONTH  # 60


# ══════════════════════════════════════════════════════════════════════════════
# Heatmap grid (custom painted)
# ══════════════════════════════════════════════════════════════════════════════

class _HeatmapGrid(QWidget):
    """Month-partitioned contribution grid: 12 months × (7 days × 5 weeks)."""

    date_hovered = Signal(object)
    date_clicked = Signal(object)

    _DAY_LABELS: list[str] = ["一", "二", "三", "四", "五", "六", "日"]
    _MONTH_NAMES = [
        "", "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
    ]
    _FLAG_SIZE = 10

    def __init__(self, model: HeatmapModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model
        self._hovered_date: date | None = None
        self._cell_size = _TARGET_CELL
        self._cell_gap = 3
        self._cell_step = _TARGET_CELL + 3

        # Highlight range (from quick-overview preset)
        self._highlight_range: tuple[date, date] | None = None
        self._highlight_label: str = ""

        self.setMouseTracking(True)
        self.setMinimumSize(600, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------
    # Sizing
    # ------------------------------------------------------------------

    def _total_width(self) -> float:
        return _LEFT_MARGIN + _TOTAL_COLS * self._cell_step + (_MONTHS_PER_YEAR - 1) * _MONTH_GAP + _RIGHT_MARGIN

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        available = self.width() - _LEFT_MARGIN - _RIGHT_MARGIN - (_MONTHS_PER_YEAR - 1) * _MONTH_GAP
        raw_step = available / _TOTAL_COLS
        self._cell_step = max(_MIN_CELL + 1, raw_step)
        self._cell_gap = max(1, min(4, int(self._cell_step * 0.15)))
        self._cell_size = int(self._cell_step - self._cell_gap)
        total_h = _TOP_MARGIN + _DAYS_PER_WEEK * self._cell_step + _BOTTOM_MARGIN + _LEGEND_HEIGHT + 6
        self.setFixedHeight(int(total_h))
        self.update()

    def refresh(self) -> None:
        if self.width() > 0 and self.height() > 0:
            self.repaint()
        else:
            self.update()

    def set_highlight_range(self, d_from: date | None, d_to: date | None, label: str = "") -> None:
        if d_from and d_to:
            self._highlight_range = (d_from, d_to)
            self._highlight_label = label
        else:
            self._highlight_range = None
            self._highlight_label = ""
        self.update()

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _month_x(self, month: int) -> float:
        """Left edge X of month block (month is 1-indexed)."""
        return _LEFT_MARGIN + (month - 1) * (_WEEKS_PER_MONTH * self._cell_step + _MONTH_GAP)

    def _cell_x(self, month: int, week: int) -> float:
        return self._month_x(month) + week * self._cell_step

    def _cell_y(self, day: int) -> float:
        return _TOP_MARGIN + day * self._cell_step

    def _month_monday(self, year: int, month: int) -> date:
        first_day = date(year, month, 1)
        return first_day - timedelta(days=first_day.weekday())

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = get_tokens()
        year = self._model.current_year()
        data = self._model.data_for_tag(None)
        max_count = self._model.max_count()

        # ── Day labels (left) ──
        font = p.font()
        font.setPointSize(7)
        font.setBold(True)
        p.setFont(font)
        for row, label in enumerate(self._DAY_LABELS):
            label_y = self._cell_y(row)
            p.setPen(QColor(t.text_secondary))
            p.drawText(
                QRect(0, int(label_y), _LEFT_MARGIN - 12, int(self._cell_step)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        # ── Cells + labels ──
        self._paint_normal(p, year, data, max_count, t)

        # ── Legend ──
        self._draw_legend(p, t)

        p.end()

    def _paint_normal(self, p: QPainter, year: int, data: dict, max_count: int, t) -> None:
        font = p.font()
        # Month labels
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        for month in range(1, 13):
            mx = self._month_x(month)
            center_x = mx + _WEEKS_PER_MONTH * self._cell_step / 2
            label_w = _WEEKS_PER_MONTH * self._cell_step
            p.setPen(QColor(t.text_secondary))
            p.drawText(
                QRect(int(center_x - label_w / 2), 1, int(label_w), _TOP_MARGIN - 3),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
                self._MONTH_NAMES[month],
            )
        # Cells
        for month in range(1, 13):
            monday = self._month_monday(year, month)
            for week in range(_WEEKS_PER_MONTH):
                for day in range(_DAYS_PER_WEEK):
                    cell_date = monday + timedelta(days=week * 7 + day)
                    belongs = (cell_date.month == month and cell_date.year == year)
                    count = data.get(cell_date, 0) if belongs else -1
                    self._draw_cell(p, month, week, day, cell_date, count, max_count, t, belongs)

        # ── Highlight range: subtle column background tint ──
        if self._highlight_range:
            d1, d2 = self._highlight_range
            highlight_cols: set[tuple[int, int]] = set()
            for month in range(1, 13):
                monday = self._month_monday(year, month)
                for week in range(_WEEKS_PER_MONTH):
                    for day in range(_DAYS_PER_WEEK):
                        cell_date = monday + timedelta(days=week * 7 + day)
                        if cell_date.month == month and cell_date.year == year and d1 <= cell_date <= d2:
                            highlight_cols.add((month, week))
            col_bg = QColor(t.accent)
            col_bg.setAlpha(22)
            for month, week in highlight_cols:
                x = self._cell_x(month, week)
                p.fillRect(
                    QRectF(x, _TOP_MARGIN, self._cell_size, _DAYS_PER_WEEK * self._cell_step),
                    col_bg,
                )

    def _draw_cell(self, p: QPainter, month: int, week: int, day: int,
                   cell_date: date, count: int, max_count: int, t, belongs: bool) -> None:
        x = self._cell_x(month, week)
        y = self._cell_y(day)
        size = int(self._cell_size)
        rect = QRect(int(x), int(y), size, size)
        self._draw_cell_content(p, rect, cell_date, count, max_count, t, belongs)

    def _draw_cell_content(self, p: QPainter, rect: QRect, cell_date: date,
                           count: int, max_count: int, t, belongs: bool) -> None:
        # ── Non-month: invisible ──
        if not belongs:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.bg_primary))
            p.drawRoundedRect(rect, 3, 3)
            return

        # ── Base: empty cell ──
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.heatmap_empty))
        p.drawRoundedRect(rect, 3, 3)

        # ── Activity / today fill ──
        if cell_date == date.today():
            # Today: accent fill + ring
            color = QColor(t.accent)
            if count == 0:
                color.setAlpha(60)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 3, 3)
            # Accent ring (prominent)
            p.setPen(QPen(QColor(t.accent), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 4, 4)
        elif count > 0:
            # Activity: accent gradient (heatmap_empty → accent)
            ratio = count / max(max_count, 1)
            empty = QColor(t.heatmap_empty)
            accent = QColor(t.accent)
            r2 = int(empty.red() + (accent.red() - empty.red()) * ratio)
            g2 = int(empty.green() + (accent.green() - empty.green()) * ratio)
            b2 = int(empty.blue() + (accent.blue() - empty.blue()) * ratio)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(r2, g2, b2))
            p.drawRoundedRect(rect, 3, 3)

        # ── Hover highlight ──
        if cell_date == self._hovered_date:
            p.setPen(QPen(QColor(t.text_primary), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 4, 4)

    def _is_in_highlight(self, d: date) -> bool:
        if self._highlight_range is None:
            return False
        return self._highlight_range[0] <= d <= self._highlight_range[1]

    def _draw_legend(self, p: QPainter, t) -> None:
        legend_y = int(_TOP_MARGIN + _DAYS_PER_WEEK * self._cell_step + _BOTTOM_MARGIN + 2)
        p.setPen(QColor(t.text_secondary))
        font = p.font()
        font.setPointSize(6)
        p.setFont(font)

        label_w = 16
        p.drawText(QRect(_LEFT_MARGIN, legend_y, label_w, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "少")

        swatch_size = 10
        gap = 1
        num_swatches = 8
        swatch_start = _LEFT_MARGIN + label_w + 2
        for i in range(num_swatches):
            sx = swatch_start + i * (swatch_size + gap)
            if i == 0:
                color = QColor(t.heatmap_empty)
            else:
                gradient = t.heatmap_gradient(7)
                color = QColor(gradient[i - 1])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(sx, legend_y + 2, swatch_size, swatch_size, 2, 2)

        p.setPen(QColor(t.text_secondary))
        p.drawText(
            QRect(swatch_start + num_swatches * (swatch_size + gap) + 2, legend_y, label_w, 14),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "多",
        )

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _date_at_pos(self, pos: QPoint) -> date | None:
        block_w = _WEEKS_PER_MONTH * self._cell_step + _MONTH_GAP
        month = int((pos.x() - _LEFT_MARGIN) / block_w) + 1
        if month < 1 or month > 12:
            return None
        offset = pos.x() - self._month_x(month)
        week = int(offset / self._cell_step)
        if week < 0 or week >= _WEEKS_PER_MONTH:
            return None
        row = int((pos.y() - _TOP_MARGIN + self._cell_gap // 2) / self._cell_step)
        if row < 0 or row >= _DAYS_PER_WEEK:
            return None
        year = self._model.current_year()
        monday = self._month_monday(year, month)
        d = monday + timedelta(days=week * 7 + row)
        if d.month != month or d.year != year:
            return None
        return d

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        d = self._date_at_pos(event.pos())
        if d != self._hovered_date:
            self._hovered_date = d
            self.date_hovered.emit(d)
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        d = self._date_at_pos(event.pos())
        if d is not None:
            self.date_clicked.emit(d)

    def leaveEvent(self, event) -> None:
        self._hovered_date = None
        self.date_hovered.emit(None)
        self.update()


# ══════════════════════════════════════════════════════════════════════════════
# CalendarHeatmapWidget (top-level)
# ══════════════════════════════════════════════════════════════════════════════

class CalendarHeatmapWidget(QWidget):
    """Heatmap: right-aligned nav + tag filter + painted grid + tooltip."""

    back_requested = Signal()

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
        self._selected_tags: list[str] = []

        start_year = date.today().year
        self._model.load_year(start_year)
        self._model.load_available_tags()

        self._tooltip = HeatmapTooltip(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(0)

        # ── Nav bar (exposed for main_window to place in combined row) ──
        self.nav_bar = QWidget()
        top_row = QHBoxLayout(self.nav_bar)
        top_row.setContentsMargins(4, 0, 4, 0)
        top_row.setSpacing(3)
        top_row.addStretch()

        self._tag_combo = DropdownWidget()
        self._tag_combo.setObjectName("heatmapTagCombo")
        self._tag_combo.currentIndexChanged.connect(self._on_tag_filter_changed)
        self._tag_combo.setFixedWidth(combo_width(6))
        top_row.addWidget(self._tag_combo)
        top_row.addSpacing(8)

        self._prev_btn = QPushButton("<")
        self._prev_btn.setObjectName("navBtn")
        self._prev_btn.setFixedWidth(22)
        self._prev_btn.clicked.connect(self._prev_year)

        self._year_label = QLabel(str(self._model.current_year()))
        self._year_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._year_label.setStyleSheet("font-weight: bold; font-size: 13px;")

        self._next_btn = QPushButton(">")
        self._next_btn.setObjectName("navBtn")
        self._next_btn.setFixedWidth(22)
        self._next_btn.clicked.connect(self._next_year)

        top_row.addWidget(self._prev_btn)
        top_row.addWidget(self._year_label)
        top_row.addWidget(self._next_btn)
        top_row.addSpacing(8)

        self._back_btn = QPushButton("↩")
        self._back_btn.setObjectName("navBtn")
        self._back_btn.setFixedWidth(26)
        self._back_btn.setToolTip("返回主界面")
        self._back_btn.clicked.connect(self.back_requested.emit)
        top_row.addWidget(self._back_btn)

        # ── Grid ──
        self._main_grid = _HeatmapGrid(self._model)
        self._main_grid.date_hovered.connect(self._on_date_hovered)
        layout.addWidget(self._main_grid)

        self._rebuild_tag_combo()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def grid(self):
        """Expose the _HeatmapGrid for signal connections."""
        return self._main_grid

    def refresh(self) -> None:
        self._model.load_year(self._model.current_year())
        self._model.load_available_tags()
        self._rebuild_tag_combo()
        self._main_grid.refresh()

    def set_year(self, year: int) -> None:
        self._model.load_year(year)
        self._year_label.setText(str(year))
        self._main_grid.refresh()

    def current_year(self) -> int:
        return self._model.current_year()

    def set_partition_id(self, partition_id: str | None) -> None:
        self._model.set_partition_id(partition_id)
        self.refresh()

    def force_refresh(self) -> None:
        """Reload data and repaint without rebuilding tag combo."""
        self._model.load_available_tags()
        self._model.load_year(self._model.current_year())
        if self._main_grid.width() > 0:
            self._main_grid.repaint()
        else:
            self._main_grid.update()

    def highlight_range(self, d_from: date | None, d_to: date | None, label: str = "") -> None:
        self._main_grid.set_highlight_range(d_from, d_to, label)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _prev_year(self) -> None:
        min_year = self._config.get("display", "heatmap_start_year", default=2026)
        if self._model.current_year() <= min_year:
            return
        self.set_year(self._model.current_year() - 1)

    def _next_year(self) -> None:
        self.set_year(self._model.current_year() + 1)

    def _jump_to_today(self) -> None:
        today = date.today()
        if self._model.current_year() != today.year:
            self.set_year(today.year)
        self._main_grid._hovered_date = today
        self._main_grid.update()

    # ------------------------------------------------------------------
    # Tag filter
    # ------------------------------------------------------------------

    def _rebuild_tag_combo(self) -> None:
        self._tag_combo.blockSignals(True)
        self._tag_combo.clear()
        self._tag_combo.addItem("全部标签", "")
        for tag in self._model.available_tags():
            self._tag_combo.addItem(f"#{tag}", tag)
        self._tag_combo.setCurrentIndex(0)
        self._tag_combo.blockSignals(False)

    def _on_tag_filter_changed(self, index: int) -> None:
        tag = self._tag_combo.itemData(index)
        if tag:
            self._model.set_tags([tag])
        else:
            self._model.set_tags([])
        self._main_grid.refresh()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_date_hovered(self, d: date | None) -> None:
        if d is None:
            self._tooltip.hide_tip()
        else:
            count = self._model.count_for_date(d)
            task_count = self._model.task_count_for_date(d)
            screen_pos = self.cursor().pos()
            self._tooltip.show_for_date(screen_pos, d, count, task_count)
