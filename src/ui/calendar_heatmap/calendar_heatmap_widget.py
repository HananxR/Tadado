"""GitHub-style calendar heatmap widget with custom painting, year nav, and tag filtering."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
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
    date_hovered = Signal(object)

    _DAY_LABELS: list[str] = ["", "一", "", "三", "", "五", ""]

    def __init__(
        self,
        model: HeatmapModel,
        colors: dict[str, str],
        tag: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._colors = colors
        self._tag = tag
        self._hovered_date: date | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(700, 128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def refresh(self) -> None:
        self.update()

    def set_tag(self, tag: str | None) -> None:
        self._tag = tag
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        year = self._model.current_year()

        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        for row, label in enumerate(self._DAY_LABELS):
            if label:
                y = _TOP_MARGIN + row * _CELL_STEP + _CELL_SIZE
                p.setPen(QColor("#888"))
                p.drawText(
                    QRect(0, y - 8, _LEFT_MARGIN - 4, 16),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    label,
                )

        self._draw_month_labels(p, year)

        data = self._model.data_for_tag(self._tag)
        max_count = max(data.values()) if data else 0

        d = self._first_monday(year)
        for col in range(53):
            for row in range(7):
                cell_date = d + timedelta(days=col * 7 + row)
                if cell_date.year != year:
                    continue
                count = data.get(cell_date, 0)
                self._draw_cell(p, col, row, cell_date, count, max_count)

    def _draw_month_labels(self, p: QPainter, year: int) -> None:
        d = self._first_monday(year)
        last_label_col = -99
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(QColor("#888"))
        month_names = [
            "", "1月", "2月", "3月", "4月", "5月", "6月",
            "7月", "8月", "9月", "10月", "11月", "12月",
        ]
        for col in range(53):
            cell_date = d + timedelta(days=col * 7)
            if cell_date.year != year:
                continue
            if col == 0 or cell_date.day <= 7:
                month_col = col
                if month_col != last_label_col + 1 and month_col != last_label_col:
                    last_label_col = month_col
                    x = _LEFT_MARGIN + col * _CELL_STEP
                    p.drawText(
                        QRect(x, 0, 40, _TOP_MARGIN),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                        month_names[cell_date.month],
                    )

    def _draw_cell(self, p: QPainter, col: int, row: int, cell_date: date, count: int, max_count: int) -> None:
        x = _LEFT_MARGIN + col * _CELL_STEP
        y = _TOP_MARGIN + row * _CELL_STEP
        rect = QRect(x, y, _CELL_SIZE, _CELL_SIZE)

        level = self._level_for_count(count, max_count)
        color_hex = self._colors.get(level, "#ebedf0")
        color = QColor(color_hex)

        if cell_date > date.today():
            color.setAlpha(40)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(rect, 2, 2)

        if cell_date == self._hovered_date:
            p.setPen(QPen(QColor("#333"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)

    def _level_for_count(self, count: int, max_count: int) -> str:
        if count == 0:
            return "level_0"
        if max_count == 0:
            return "level_1"
        ratio = count / max_count
        if ratio <= 0.25:
            return "level_1"
        if ratio <= 0.5:
            return "level_2"
        if ratio <= 0.75:
            return "level_3"
        return "level_4"

    @staticmethod
    def _first_monday(year: int) -> date:
        jan1 = date(year, 1, 1)
        return jan1 - timedelta(days=jan1.weekday())

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

    def sizeHint(self) -> QSize:
        return QSize(_LEFT_MARGIN + 53 * _CELL_STEP + _RIGHT_MARGIN, 130)

    def minimumSizeHint(self) -> QSize:
        return QSize(700, 128)


class CalendarHeatmapWidget(QWidget):
    """Complete heatmap widget: year nav + tag selector + painted grid."""

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

        start_year = config.get("display", "heatmap_start_year", default=2026)
        self._model.load_year(start_year)
        self._model.load_available_tags()
        self._independent_mode = False
        self._tag_grids: dict[str, _HeatmapGrid] = {}
        self._selected_tags: list[str] = []
        self._max_tag_selection = 10

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)

        # --- Year navigation ---
        nav = QHBoxLayout()
        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedWidth(28)
        self._prev_btn.clicked.connect(self._prev_year)
        self._year_label = QLabel(str(self._model.current_year()))
        self._year_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._year_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._next_btn = QPushButton(">")
        self._next_btn.setFixedWidth(28)
        self._next_btn.clicked.connect(self._next_year)

        nav.addStretch()
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._year_label)
        nav.addWidget(self._next_btn)
        nav.addStretch()
        layout.addLayout(nav)

        # --- Tag selector: dropdown with multi-select (menu stays open) ---
        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        tag_row.addWidget(QLabel("标签筛选:"))
        tag_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._tag_btn = QPushButton("选择标签...")
        self._tag_btn.setFixedWidth(100)
        self._tag_btn.clicked.connect(self._show_tag_menu)
        tag_row.addWidget(self._tag_btn)

        self._tag_pills_label = QLabel("全部标签")
        self._tag_pills_label.setStyleSheet("color: #888; font-size: 10px;")
        tag_row.addWidget(self._tag_pills_label)

        tag_row.addSpacing(16)

        self._mode_combo_label = QLabel("显示:")
        tag_row.addWidget(self._mode_combo_label)
        from PySide6.QtWidgets import QComboBox
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("合并显示", "merge")
        self._mode_combo.addItem("独立显示", "independent")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        tag_row.addWidget(self._mode_combo)

        tag_row.addStretch()
        layout.addLayout(tag_row)

        # --- Grid area (centered) ---
        grid_wrapper = QHBoxLayout()
        grid_wrapper.addStretch()
        self._grid_stack = QVBoxLayout()
        self._grid_stack.setSpacing(12)

        colors = self._config.heatmap_colors
        self._main_grid = _HeatmapGrid(self._model, colors)
        self._main_grid.date_selected.connect(self._on_date_selected)
        self._main_grid.date_hovered.connect(self._on_date_hovered)
        self._grid_stack.addWidget(self._main_grid)

        grid_wrapper.addLayout(self._grid_stack)
        grid_wrapper.addStretch()
        layout.addLayout(grid_wrapper)

        # --- Hover tooltip ---
        self._tooltip = QLabel()
        self._tooltip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tooltip.setStyleSheet("color: #888; font-size: 11px;")
        self._tooltip.setFixedHeight(18)
        layout.addWidget(self._tooltip)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self._model.load_year(self._model.current_year())
        self._model.load_available_tags()
        self._update_pills()
        self._main_grid.refresh()
        for g in self._tag_grids.values():
            g.refresh()

    def set_year(self, year: int) -> None:
        self._model.load_year(year)
        self._model.load_available_tags()
        self._year_label.setText(str(year))
        self._rebuild_tag_grids()
        self._main_grid.refresh()

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
    # Tag filter — multi-select popup that stays open
    # ------------------------------------------------------------------

    def _show_tag_menu(self) -> None:
        menu = QMenu(self)
        available = self._model.available_tags()

        if not available:
            noop = menu.addAction("(暂无标签)")
            noop.setEnabled(False)
            menu.exec(self._tag_btn.mapToGlobal(self._tag_btn.rect().bottomLeft()))
            return

        # "全部" as first item
        all_item = QListWidgetItem("  全部标签")
        all_item.setCheckState(
            Qt.CheckState.Checked if not self._selected_tags else Qt.CheckState.Unchecked
        )
        all_item.setData(Qt.ItemDataRole.UserRole, "__all__")

        list_widget = QListWidget()
        list_widget.setMaximumHeight(260)
        list_widget.setStyleSheet("QListWidget { border: none; }")
        list_widget.addItem(all_item)

        for tag in available:
            item = QListWidgetItem(f"  #{tag}")
            item.setCheckState(
                Qt.CheckState.Checked if tag in self._selected_tags else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, tag)
            list_widget.addItem(item)

        list_widget.itemChanged.connect(
            lambda item: self._on_list_item_changed(item, list_widget)
        )

        widget_action = QWidgetAction(menu)
        widget_action.setDefaultWidget(list_widget)
        menu.addAction(widget_action)

        menu.addSeparator()
        done = menu.addAction("  完成")
        done.triggered.connect(menu.close)

        menu.exec(self._tag_btn.mapToGlobal(self._tag_btn.rect().bottomLeft()))

    def _on_list_item_changed(self, item: QListWidgetItem, list_widget: QListWidget) -> None:
        tag = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked

        if tag == "__all__":
            if checked:
                # "全部" checked — clear all individual selections
                self._selected_tags = []
                list_widget.blockSignals(True)
                for i in range(1, list_widget.count()):
                    list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)
                list_widget.blockSignals(False)
        else:
            if checked:
                if tag not in self._selected_tags:
                    if len(self._selected_tags) >= self._max_tag_selection:
                        list_widget.blockSignals(True)
                        item.setCheckState(Qt.CheckState.Unchecked)
                        list_widget.blockSignals(False)
                        return
                    self._selected_tags.append(tag)
            else:
                if tag in self._selected_tags:
                    self._selected_tags.remove(tag)

            # If individual tags selected, uncheck "全部"
            if self._selected_tags:
                list_widget.blockSignals(True)
                list_widget.item(0).setCheckState(Qt.CheckState.Unchecked)
                list_widget.blockSignals(False)
            else:
                list_widget.blockSignals(True)
                list_widget.item(0).setCheckState(Qt.CheckState.Checked)
                list_widget.blockSignals(False)

        self._apply_tag_filter()

    def _apply_tag_filter(self) -> None:
        self._model.set_tags(self._selected_tags)
        self._rebuild_tag_grids()
        self._main_grid.refresh()
        self._update_pills()

    def _update_pills(self) -> None:
        if not self._selected_tags:
            self._tag_pills_label.setText("全部标签")
        else:
            shown = ", ".join(self._selected_tags[:3])
            if len(self._selected_tags) > 3:
                shown += f" 等{len(self._selected_tags)}个"
            self._tag_pills_label.setText(shown)

    # ------------------------------------------------------------------
    # Display mode
    # ------------------------------------------------------------------

    def _on_mode_changed(self, index: int) -> None:
        mode = self._mode_combo.itemData(index)
        self._independent_mode = (mode == "independent")
        if self._independent_mode:
            self._model.load_per_tag(self._model.current_year())
        self._rebuild_tag_grids()

    def _rebuild_tag_grids(self) -> None:
        while self._grid_stack.count() > 1:
            item = self._grid_stack.takeAt(self._grid_stack.count() - 1)
            if item.widget():
                item.widget().deleteLater()
        self._tag_grids.clear()

        if self._independent_mode:
            tags_to_show = self._selected_tags if self._selected_tags else self._model.available_tags()
            colors = self._config.heatmap_colors
            for tag in tags_to_show:
                grid = _HeatmapGrid(self._model, colors, tag=tag)
                grid.date_selected.connect(self._on_date_selected)
                grid.date_hovered.connect(self._on_date_hovered)
                grid.setMinimumSize(700, 100)
                self._tag_grids[tag] = grid

                label = QLabel(f"  #{tag}")
                label.setStyleSheet("font-weight: bold; color: #888; font-size: 11px;")
                self._grid_stack.addWidget(label)
                self._grid_stack.addWidget(grid)

        self._main_grid.setVisible(not self._independent_mode)
        self._tooltip.setVisible(not self._independent_mode)

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
