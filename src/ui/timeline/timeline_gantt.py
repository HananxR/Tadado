"""TimelineTableView —— 时间轴（甘特）Qt 视图层。

结构：

* :class:`TimelineTableModel`（``QAbstractTableModel``）—— 2 列：``任务`` / ``时间轴``
* :class:`TimelineGanttDelegate`（``QStyledItemDelegate``）—— 绘制日期网格、今天竖线、
  任务色条（填充=进度、端点=截止、状态着色、逾期描边）
* :class:`TimelineTableView`（``QTableView``）—— 组装模型/委托，并在视口上方绘制日期轴

坐标系统一：轴由 ``(x0, width, axis_len)`` 决定，``cell_w = width / axis_len``；
委托使用 ``option.rect``（视口坐标），视图表头使用 ``columnViewportPosition(1)``
与 ``columnWidth(1)``，两者一致（第 1 列为唯一拉伸列）。
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QStyledItemDelegate, QTableView

from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens
from .timeline_model import TimelineData, TimelineRow

#: 标题列固定宽度
TITLE_COL_WIDTH = 248
#: 单行高度
ROW_HEIGHT = 40
#: 日期轴表头高度
HEADER_HEIGHT = 36
#: 色条高度与圆角
BAR_HEIGHT = 18
BAR_RADIUS = 5.0
#: 单元格过窄时省略日期文字的阈值
_MIN_LABEL_WIDTH = 22


def axis_cell_width(rect_width: float, axis_len: int) -> float:
    """轴内每天占用的像素宽度；``axis_len <= 0`` 时返回 0.0。

    宽度为 0 时仍返回 1.0，保证调用方不会画出重叠的负宽度色条。
    """
    if axis_len <= 0:
        return 0.0
    return max(1.0, float(rect_width) / int(axis_len))


def _status_color(status_value: str) -> QColor:
    return QColor(TaskStatus.from_string(status_value).display_color)


class TimelineTableModel(QAbstractTableModel):
    """把 :class:`TimelineData` 暴露为 2 列表格模型。"""

    HEADERS = ("任务", "时间轴")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: TimelineData | None = None

    # ── 数据 ──

    def set_data(self, data: TimelineData | None) -> None:
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    @property
    def timeline(self) -> TimelineData | None:
        return self._data

    def row_at(self, row: int) -> TimelineRow | None:
        if self._data is None or not (0 <= row < len(self._data.rows)):
            return None
        return self._data.rows[row]

    # ── QAbstractTableModel ──

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return 0 if self._data is None else len(self._data.rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        row = self.row_at(index.row())
        if row is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
            return row.title
        if role == Qt.ItemDataRole.ToolTipRole:
            status = TaskStatus.from_string(row.status).display_name
            return (
                f"{row.title}\n状态：{status} ｜ 进度：{row.progress}%\n"
                f"起止：{row.start.isoformat()} → {row.end.isoformat()}"
            )
        return None


class TimelineGanttDelegate(QStyledItemDelegate):
    """绘制单行的甘特内容（第 1 列）。"""

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: D102
        model = index.model()
        row = model.row_at(index.row()) if hasattr(model, "row_at") else None
        data = getattr(model, "timeline", None)
        if row is None or data is None:
            return

        t = get_tokens()
        rect = QRectF(option.rect)
        axis_len = data.axis_len
        cell_w = axis_cell_width(rect.width(), axis_len)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 日期分隔线
        grid_pen = QPen(QColor(t.border_primary))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        for i in range(1, axis_len):
            x = rect.left() + i * cell_w
            painter.drawLine(int(x), int(rect.top()) + 4, int(x), int(rect.bottom()) - 4)

        # 今天竖线
        if data.today_index is not None:
            tx = rect.left() + (data.today_index + 0.5) * cell_w
            accent_pen = QPen(QColor(t.accent))
            accent_pen.setWidth(1)
            painter.setPen(accent_pen)
            painter.drawLine(int(tx), int(rect.top()), int(tx), int(rect.bottom()))

        # 任务色条
        start_cell = row.clipped_offset
        span = row.clipped_span(axis_len)
        if span > 0:
            bar_left = rect.left() + start_cell * cell_w + 1.0
            bar_right = rect.left() + (start_cell + span) * cell_w - 1.0
            if bar_right - bar_left < 2.0:
                bar_right = bar_left + 2.0
            bar_top = rect.center().y() - BAR_HEIGHT / 2.0
            bar = QRectF(bar_left, bar_top, bar_right - bar_left, float(BAR_HEIGHT))

            color = _status_color(row.status)
            # 底色（低透明度）
            base = QColor(color)
            base.setAlpha(60)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(base)
            painter.drawRoundedRect(bar, BAR_RADIUS, BAR_RADIUS)

            # 进度填充
            progress = max(0, min(100, int(row.progress)))
            if progress > 0:
                fill = QColor(color)
                fill.setAlpha(200)
                painter.setBrush(fill)
                fill_w = bar.width() * progress / 100.0
                painter.drawRoundedRect(
                    QRectF(bar.left(), bar.top(), max(2.0, fill_w), bar.height()),
                    BAR_RADIUS,
                    BAR_RADIUS,
                )

            # 描边（逾期用 danger）
            border = QColor(t.danger) if row.overdue else color
            border_pen = QPen(border)
            border_pen.setWidth(1)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(bar, BAR_RADIUS, BAR_RADIUS)

            # 截止端点
            dot = QColor(t.danger) if row.overdue else QColor(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot)
            painter.drawEllipse(
                QRectF(bar.right() - 3.0, bar.center().y() - 3.0, 6.0, 6.0)
            )

        painter.restore()

    def sizeHint(self, option, index):  # noqa: N802, D102
        hint = super().sizeHint(option, index)
        hint.setHeight(ROW_HEIGHT)
        return hint


class TimelineTableView(QTableView):
    """时间轴表格：行=任务，右侧为目标日期轴。

    Signals:
        task_selected(task_id): 单击选中
        task_activated(task_id): 双击（打开维护抽屉 / 编辑器）
    """

    task_selected = Signal(str)
    task_activated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: TimelineData | None = None

        self._table_model = TimelineTableModel(self)
        self.setModel(self._table_model)
        self.setItemDelegateForColumn(1, TimelineGanttDelegate(self))

        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.setViewportMargins(0, HEADER_HEIGHT, 0, 0)
        self.setColumnWidth(0, TITLE_COL_WIDTH)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.clicked.connect(self._emit_selected)
        self.doubleClicked.connect(self._emit_activated)

        from ...utils.theme_registry import register_theme_aware

        register_theme_aware(self)

    def refresh_theme(self) -> None:
        """主题切换：日期轴表头与色条在绘制时读令牌，重绘即可。"""
        self.viewport().update()
        self.update()

    # ── 数据 ──

    def set_timeline(self, data: TimelineData | None) -> None:
        self._data = data
        self._table_model.set_data(data)
        self.viewport().update()
        self.update()

    @property
    def timeline(self) -> TimelineData | None:
        return self._data

    @property
    def table_model(self) -> TimelineTableModel:
        return self._table_model

    def selected_task_id(self) -> str | None:
        rows = self.selectionModel().selectedRows() if self.selectionModel() else []
        if not rows:
            return None
        row = self._table_model.row_at(rows[0].row())
        return row.task_id if row else None

    # ── 交互 ──

    def _emit_selected(self, index: QModelIndex) -> None:
        row = self._table_model.row_at(index.row())
        if row:
            self.task_selected.emit(row.task_id)

    def _emit_activated(self, index: QModelIndex) -> None:
        row = self._table_model.row_at(index.row())
        if row:
            self.task_activated.emit(row.task_id)

    # ── 绘制日期轴表头 ──

    def _axis_geometry(self) -> tuple[float, float, int]:
        """返回 (x0, width, axis_len)：第 1 列在视口坐标下的位置与宽度。"""
        x0 = float(self.columnViewportPosition(1))
        width = float(self.columnWidth(1))
        axis_len = self._data.axis_len if self._data else 0
        return x0, width, axis_len

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._data is None:
            return
        x0, width, axis_len = self._axis_geometry()
        if axis_len <= 0 or width <= 0:
            return

        t = get_tokens()
        # 表头位于 viewport 上方的 margin 带 → 画在 widget 坐标上
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        header_rect = QRectF(0, 0, float(self.width()), float(HEADER_HEIGHT))
        painter.fillRect(header_rect, QColor(t.bg_secondary))
        painter.setClipRect(header_rect)

        cell_w = axis_cell_width(width, axis_len)
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
        painter.setFont(font)

        for i, day in enumerate(self._data.days):
            cx = x0 + i * cell_w
            if cx > header_rect.right():
                break
            sep = QPen(QColor(t.border_primary))
            sep.setWidth(1)
            painter.setPen(sep)
            painter.drawLine(
                int(cx), int(header_rect.top()) + 7, int(cx), int(header_rect.bottom())
            )

            if cell_w >= _MIN_LABEL_WIDTH or i % 2 == 0:
                color = QColor(t.text_secondary)
                if day.weekday() >= 5:
                    color = QColor(t.text_disabled)
                if self._data.today_index == i:
                    color = QColor(t.accent)
                painter.setPen(QPen(color))
                painter.drawText(
                    QRectF(cx, header_rect.top(), cell_w, header_rect.height()),
                    int(Qt.AlignmentFlag.AlignCenter),
                    f"{day.month}/{day.day}",
                )

        if self._data.today_index is not None:
            tx = x0 + (self._data.today_index + 0.5) * cell_w
            pen = QPen(QColor(t.accent))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(
                int(tx), int(header_rect.top()), int(tx), int(header_rect.bottom())
            )
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.update()  # 表头宽度随视图变化


__all__ = [
    "HEADER_HEIGHT",
    "ROW_HEIGHT",
    "TITLE_COL_WIDTH",
    "TimelineGanttDelegate",
    "TimelineTableModel",
    "TimelineTableView",
    "axis_cell_width",
]
