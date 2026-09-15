"""TaskGraphView —— 任务图谱画布（自绘 QWidget）。

自绘而非 ``QGraphicsScene``：节点/箭线数量在任务图谱量级（数百），
自绘更易做离屏渲染断言（渲染进 QPixmap 校验像素），且避免了
QGraphicsItem 生命周期与缩放的额外复杂度。

交互：滚轮缩放、拖拽平移、悬停高亮（含一跳邻居）、双击任务节点 → 打开任务。
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...models.task_status import TaskStatus
from ...services.task_graph import GraphEdge, GraphNode
from ...utils.design_tokens import get_tokens
from .graph_layout import force_directed_layout, neighbour_map

#: 各类节点半径
NODE_RADIUS = {"partition": 16.0, "task": 11.0, "tag": 8.0}
#: 命中判定半径（略大于绘制半径，便于鼠标拾取）
HIT_RADIUS = {"partition": 20.0, "task": 15.0, "tag": 12.0}
#: 大于该缩放才绘制标签，避免拥挤
LABEL_MIN_SCALE = 0.75
_DRAG_THRESHOLD = 4


class TaskGraphView(QWidget):
    """力导向任务图谱。

    Signals:
        task_activated(task_id): 双击任务节点
        node_hovered(node_id): 悬停节点变化（离开为 ""）
    """

    task_activated = Signal(str)
    node_hovered = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("taskGraphView")
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._nodes: tuple[GraphNode, ...] = ()
        self._edges: tuple[GraphEdge, ...] = ()
        self._positions: dict[str, tuple[float, float]] = {}
        self._neighbours: dict[str, set[str]] = {}
        self._variant = 0
        self._scale = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._hovered = ""
        self._drag_origin: QPointF | None = None
        self._drag_offset_start = QPointF(0.0, 0.0)
        self._dragged = False

        from ...utils.theme_registry import register_theme_aware

        register_theme_aware(self)

    def refresh_theme(self) -> None:
        """主题切换：节点/箭线在绘制时读令牌，重绘即可。"""
        self.update()

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------

    def set_graph(self, nodes: Sequence[GraphNode], edges: Sequence[GraphEdge]) -> None:
        self._nodes = tuple(nodes)
        self._edges = tuple(edges)
        self._neighbours = neighbour_map((e.source, e.target) for e in self._edges)
        self.relayout(reset_variant=True)

    @property
    def nodes(self) -> tuple[GraphNode, ...]:
        return self._nodes

    @property
    def edges(self) -> tuple[GraphEdge, ...]:
        return self._edges

    @property
    def positions(self) -> dict[str, tuple[float, float]]:
        return dict(self._positions)

    def relayout(self, *, reset_variant: bool = False) -> None:
        """重算布局；``reset_variant=False`` 时换一个变体（「重新布局」按钮）。"""
        if reset_variant:
            self._variant = 0
        else:
            self._variant += 1
        self._positions = force_directed_layout(
            [n.id for n in self._nodes],
            [(e.source, e.target) for e in self._edges],
            float(max(1, self.width())),
            float(max(1, self.height())),
            variant=self._variant,
        )
        self.update()

    # ------------------------------------------------------------------
    # 缩放 / 平移
    # ------------------------------------------------------------------

    @property
    def scale_factor(self) -> float:
        return self._scale

    def zoom_in(self) -> None:
        self._set_scale(self._scale * 1.2)

    def zoom_out(self) -> None:
        self._set_scale(self._scale / 1.2)

    def reset_zoom(self) -> None:
        self._set_scale(1.0)
        self._offset = QPointF(0.0, 0.0)
        self.update()

    def _set_scale(self, scale: float) -> None:
        self._scale = min(3.0, max(0.3, float(scale)))
        self.update()

    def _to_widget(self, x: float, y: float) -> QPointF:
        """画布坐标 → 控件坐标（以中心为缩放原点）。"""
        cx, cy = self.width() / 2.0, self.height() / 2.0
        return QPointF(
            cx + (x - cx) * self._scale + self._offset.x(),
            cy + (y - cy) * self._scale + self._offset.y(),
        )

    def node_at(self, x: float, y: float) -> str:
        """控件坐标下命中的节点 id（无则空串）。"""
        best, best_dist = "", float("inf")
        for node in self._nodes:
            px, py = self._positions.get(node.id, (0.0, 0.0))
            point = self._to_widget(px, py)
            dist = ((point.x() - x) ** 2 + (point.y() - y) ** 2) ** 0.5
            radius = HIT_RADIUS.get(node.kind, 12.0) * max(0.7, self._scale)
            if dist <= radius and dist < best_dist:
                best, best_dist = node.id, dist
        return best

    @property
    def hovered_node_id(self) -> str:
        return self._hovered

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        if self._drag_origin is not None:
            delta = pos - self._drag_origin
            if abs(delta.x()) > _DRAG_THRESHOLD or abs(delta.y()) > _DRAG_THRESHOLD:
                self._dragged = True
                self._offset = self._drag_offset_start + delta
                self.update()
            return

        hovered = self.node_at(pos.x(), pos.y())
        if hovered != self._hovered:
            self._hovered = hovered
            self.node_hovered.emit(hovered)
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position()
            self._drag_offset_start = QPointF(self._offset)
            self._dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_origin = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if not self._dragged and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            node_id = self.node_at(pos.x(), pos.y())
            if node_id.startswith("task:"):
                self.task_activated.emit(node_id.split(":", 1)[1])

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        node_id = self.node_at(pos.x(), pos.y())
        if node_id.startswith("task:"):
            self.task_activated.emit(node_id.split(":", 1)[1])

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.angleDelta().y() > 0:
            self._set_scale(self._scale * 1.15)
        else:
            self._set_scale(self._scale / 1.15)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        t = get_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(t.bg_primary))

        if not self._nodes:
            painter.setPen(QPen(QColor(t.text_secondary)))
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "暂无图谱数据")
            painter.end()
            return

        highlight = set()
        if self._hovered:
            highlight = {self._hovered} | self._neighbours.get(self._hovered, set())

        # 边
        for edge in self._edges:
            p1 = self._positions.get(edge.source)
            p2 = self._positions.get(edge.target)
            if p1 is None or p2 is None:
                continue
            dim = bool(highlight) and not (
                edge.source in highlight and edge.target in highlight
            )
            if edge.kind == "link":
                pen = QPen(QColor(t.accent))
                pen.setStyle(Qt.PenStyle.DashLine)
            else:
                pen = QPen(QColor(t.border_primary))
            pen.setWidth(2 if edge.kind == "link" else 1)
            if dim:
                color = pen.color()
                color.setAlpha(40)
                pen.setColor(color)
            painter.setPen(pen)
            painter.drawLine(self._to_widget(*p1), self._to_widget(*p2))

        # 节点
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        painter.setFont(font)
        for node in self._nodes:
            position = self._positions.get(node.id)
            if position is None:
                continue
            center = self._to_widget(*position)
            radius = NODE_RADIUS.get(node.kind, 10.0) * max(0.6, self._scale)
            fill, border = self._node_colors(node, t)
            dim = bool(highlight) and node.id not in highlight
            if dim:
                fill.setAlpha(50)
                border.setAlpha(50)

            painter.setPen(QPen(border, 2.0 if node.id == self._hovered else 1.2))
            painter.setBrush(fill)
            painter.drawEllipse(center, radius, radius)

            if self._scale >= LABEL_MIN_SCALE or node.id == self._hovered:
                painter.setPen(QPen(QColor(t.text_primary if not dim else t.text_disabled)))
                label = node.label if len(node.label) <= 12 else node.label[:11] + "…"
                painter.drawText(
                    QRectF(center.x() - 60.0, center.y() + radius + 1.0, 120.0, 16.0),
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                    label,
                )
        painter.end()

    @staticmethod
    def _node_colors(node: GraphNode, t) -> tuple[QColor, QColor]:
        if node.kind == "partition":
            return QColor(t.accent), QColor(t.accent)
        if node.kind == "tag":
            fill = QColor(t.bg_secondary)
            return fill, QColor(t.accent)
        color = QColor(TaskStatus.from_string(node.status or "TODO").display_color)
        return color, color


__all__ = ["HIT_RADIUS", "NODE_RADIUS", "TaskGraphView"]
