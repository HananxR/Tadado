"""任务图谱页（阶段 6）— 力导向关系网络。

页头 + 工具行（状态 chips / 仅看任务关联 / 隐藏已完成 / 重新布局）+ 图谱画布。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..graph import GraphController, TaskGraphView

#: 状态 chips：(键, 显示名)
_STATUS_CHIPS = (
    ("all", "全部"),
    ("doing", "进行中"),
    ("overdue", "逾期"),
    ("week", "本周"),
)


def build(mw) -> QWidget:
    """Build the graph page."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(6)

    # ── 页头 ──
    header = QWidget()
    header_row = QHBoxLayout(header)
    header_row.setContentsMargins(0, 0, 0, 0)
    header_row.setSpacing(8)
    # 这是**页面标题**，不是卡片标题：此前 15px 让它比任务页的 21px 小一档，
    # 同一层级在不同页面大小不一，正是「字阶散掉」的典型症状。
    title = QLabel("任务图谱")
    title.setObjectName("pageTitle")
    header_row.addWidget(title)
    desc = QLabel("任务 × 标签 × 分区 × [[链接]] 关系网络 · 悬停高亮 · 双击直达任务")
    desc.setObjectName("pageDesc")
    header_row.addWidget(desc)
    header_row.addStretch()
    layout.addWidget(header)

    # ── 工具行 ──
    tools = QWidget()
    tools_row = QHBoxLayout(tools)
    tools_row.setContentsMargins(0, 0, 0, 0)
    tools_row.setSpacing(6)

    chips: dict[str, QPushButton] = {}
    for key, label in _STATUS_CHIPS:
        btn = QPushButton(f"{label}")
        btn.setObjectName("graphChip")
        btn.setCheckable(True)
        btn.setChecked(key == "all")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("graphFilter", key)
        chips[key] = btn
        tools_row.addWidget(btn)

    only_rel = QPushButton("仅看任务关联")
    only_rel.setObjectName("graphChip")
    only_rel.setCheckable(True)
    hide_done = QPushButton("隐藏已完成")
    hide_done.setObjectName("graphChip")
    hide_done.setCheckable(True)
    relayout_btn = QPushButton("重新布局")
    relayout_btn.setObjectName("graphChip")
    tools_row.addWidget(only_rel)
    tools_row.addWidget(hide_done)
    tools_row.addWidget(relayout_btn)
    tools_row.addStretch()

    zoom_out = QPushButton("−")
    zoom_in = QPushButton("＋")
    zoom_reset = QPushButton("1:1")
    for btn in (zoom_out, zoom_reset, zoom_in):
        btn.setObjectName("graphChip")
        btn.setFixedWidth(34)
        tools_row.addWidget(btn)
    layout.addWidget(tools)

    # ── 画布 ──
    view = TaskGraphView()
    layout.addWidget(view, 1)

    controller = GraphController(mw._task_service, view, parent=mw)

    def _select_chip(clicked_btn: QPushButton) -> None:
        """状态 chips 互斥：被点者选中，其余取消。"""
        for _key, btn in chips.items():
            btn.setChecked(btn is clicked_btn)
        controller.set_filter(str(clicked_btn.property("graphFilter")))

    for _key, btn in chips.items():
        btn.clicked.connect(lambda _checked=False, b=btn: _select_chip(b))

    only_rel.toggled.connect(controller.set_only_related)
    hide_done.toggled.connect(controller.set_hide_done)
    relayout_btn.clicked.connect(controller.relayout)
    zoom_in.clicked.connect(view.zoom_in)
    zoom_out.clicked.connect(view.zoom_out)
    zoom_reset.clicked.connect(view.reset_zoom)
    controller.task_activated.connect(mw._on_graph_task_activated)

    # 暴露给 MainWindow（分区切换/主题刷新/单测）
    mw._graph_view = view
    mw._graph_ctl = controller
    mw._graph_chips = chips

    controller.refresh()
    return page
