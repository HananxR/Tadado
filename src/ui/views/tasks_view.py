"""任务页（page-tasks）构建 —— 对齐 UI 原型 ``resources/ui-mockup/tadado-2.0.html``。

单列卡片流布局（不再有右侧常驻编辑器）::

    页头    任务 ｜ 单击选中 · 双击或右键打开维护抽屉 …        [＋ 新建任务]
    工具行  [🔍 搜索标题或标签…] [全部 28][逾期 1][待办 14][进行中 7][已完成 6]
            ………………………… [排序：截止优先 ▾] [本周 | 本月 | 近 30 天]
    时间轴  卡片容器（行=任务，右轴=日期）
    图例    色条 = 起止区间 · 填充 = 进度 · 端点 = 截止 · │ 今天

编辑走 :class:`~src.ui.drawer.TaskDrawer`（双击 / 右键唤起），新建走对话框。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...models.task_status import TaskStatus
from ...utils.design_tokens import get_tokens
from ...utils.widget_utils import combo_width
from ..calendar_heatmap.calendar_heatmap_widget import CalendarHeatmapWidget
from ..widgets.calendar_popup import CalendarPopup  # noqa: F401  (moved import)
from ..widgets.dropdown import DropdownWidget
from ..widgets.segmented_control import SegmentedControl

#: 状态快捷筛选：key → (显示名, TaskStatus | None)
STATUS_FILTERS: tuple[tuple[str, str, TaskStatus | None], ...] = (
    ("all", "全部", None),
    ("overdue", "逾期", TaskStatus.OVERDUE),
    ("todo", "待办", TaskStatus.TODO),
    ("doing", "进行中", TaskStatus.DOING),
    ("done", "已完成", TaskStatus.DONE),
)

#: 时间轴粒度分段（原型 ``#ttRange``）
TIMELINE_RANGES: tuple[tuple[str, str], ...] = (
    ("本周", "week"),
    ("本月", "month"),
    ("近 30 天", "30d"),
)

_PAGE_DESC = "单击选中 · 双击或右键打开维护抽屉 · 保存后自动收起 · Esc 关闭"


def build(mw) -> QWidget:
    """构建任务页（单列卡片流，对齐 2.0 原型）。"""
    page = QWidget()
    page.setStyleSheet(_page_qss())
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    # 密码遮罩需要一个可切换的堆叠容器（PartitionController 依赖该属性名）
    mw._splitter_container = QWidget()
    mw._splitter_stack = QStackedLayout(mw._splitter_container)
    mw._splitter_stack.setContentsMargins(0, 0, 0, 0)
    mw._splitter_stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

    # 居中窄栏（原型 .inner: max-width:1320px; margin:0 auto）
    centered = QWidget()
    center_row = QHBoxLayout(centered)
    center_row.setContentsMargins(0, 0, 0, 0)
    center_row.setSpacing(0)

    content = QWidget()
    content.setMaximumWidth(1320)
    col = QVBoxLayout(content)
    col.setContentsMargins(22, 16, 28, 18)
    col.setSpacing(10)

    col.addWidget(_build_header(mw))
    col.addWidget(_build_tools(mw))
    col.addWidget(_build_timeline_card(mw), 1)
    col.addWidget(_build_legend())

    center_row.addStretch(1)
    center_row.addWidget(content, 1)
    center_row.addStretch(1)
    mw._splitter_stack.addWidget(centered)

    # 分区密码遮罩
    mw._partition_mask = QWidget()
    mw._partition_mask.setObjectName("partitionMask")
    mask_layout = QVBoxLayout(mw._partition_mask)
    mask_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mask_hint = QLabel("此分区已加密\n请输入密码查看内容")
    mask_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mask_hint.setObjectName("emptyStateTitle")
    mask_hint.setStyleSheet("background: transparent; border: none;")
    mask_layout.addWidget(mask_hint)
    unlock_btn = QPushButton("输入密码解锁")
    unlock_btn.setObjectName("saveBtn")
    unlock_btn.setFixedWidth(140)
    # 延迟连接：_partition_ctrl 在 _setup_central_widget 之后创建
    unlock_btn.clicked.connect(lambda: mw._partition_ctrl.unlock())
    mask_btn_row = QHBoxLayout()
    mask_btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mask_btn_row.addWidget(unlock_btn)
    mask_layout.addLayout(mask_btn_row)
    mw._splitter_stack.addWidget(mw._partition_mask)
    mw._splitter_stack.setCurrentIndex(0)

    outer.addWidget(mw._splitter_container)

    # 热力图宿主：分析页复用（在此创建以保持单例与分区联动）
    mw._heatmap_widget = CalendarHeatmapWidget(mw._task_service, mw._config)
    mw._heatmap_widget.back_requested.connect(lambda: mw._switch_view("edit"))

    return page


# ----------------------------------------------------------------------
# 局部样式（对齐原型 design tokens：页头 / chips / 输入框 / 图例）
# ----------------------------------------------------------------------


def _page_qss() -> str:
    """任务页局部样式；只针对明确 objectName，不会波及时间轴表格。"""
    t = get_tokens()
    return (
        # 页头字号已上移到 base.qss 的展示层字阶（#pageTitle / #pageDesc），
        # 这里只保留本页独有的控件样式，避免同一层级在不同页面各写各的。
        f"QPushButton#primaryBtn {{"
        f" background: {t.accent}; color: {t.text_on_accent}; border: 0;"
        f" border-radius: 8px; padding: 7px 16px; font-size: 12.5px;"
        f" font-weight: 500; }}"
        f"QPushButton#primaryBtn:hover {{ background: {t.accent_hover}; }}"
        f"QPushButton#statusChip {{"
        f" background: {t.surface_raised};"
        f" border: 1px solid {t.border_primary};"
        f" border-radius: 999px; padding: 3px 11px;"
        f" font-size: 12px; color: {t.text_secondary}; }}"
        f"QPushButton#statusChip:hover {{"
        f" border-color: {t.accent}; color: {t.accent}; }}"
        f"QPushButton#statusChip:checked {{"
        f" background: {t.accent}; border-color: {t.accent};"
        f" color: {t.text_on_accent}; }}"
        f"QLineEdit#timelineSearch {{"
        f" background: {t.surface_raised};"
        f" border: 1px solid {t.border_primary};"
        f" border-radius: 8px; padding: 6px 12px; font-size: 12.5px; }}"
        f"QLineEdit#timelineSearch:focus {{ border-color: {t.accent}; }}"
        f"QLabel#timelineLegend {{ font-size: 10.5px; color: {t.text_disabled}; }}"
        f"QLabel#timelineLegendToday {{"
        f" font-size: 10.5px; color: {t.accent}; }}"
    )


# ----------------------------------------------------------------------
# 页头
# ----------------------------------------------------------------------


def _build_header(mw) -> QWidget:
    header = QWidget()
    row = QHBoxLayout(header)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(14)

    title_col = QVBoxLayout()
    title_col.setContentsMargins(0, 0, 0, 0)
    title_col.setSpacing(2)

    title = QLabel("任务")
    title.setObjectName("pageTitle")
    desc = QLabel(_PAGE_DESC)
    desc.setObjectName("pageDesc")
    title_col.addWidget(title)
    title_col.addWidget(desc)
    row.addLayout(title_col)
    row.addStretch(1)

    mw._new_task_btn = QPushButton("＋ 新建任务")
    mw._new_task_btn.setObjectName("primaryBtn")
    mw._new_task_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    row.addWidget(mw._new_task_btn, 0, Qt.AlignmentFlag.AlignBottom)
    return header


# ----------------------------------------------------------------------
# 工具行
# ----------------------------------------------------------------------


def _build_tools(mw) -> QWidget:
    from ..timeline import TimelineModel

    tools = QWidget()
    row = QHBoxLayout(tools)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    # 搜索
    mw._timeline_search = QLineEdit()
    mw._timeline_search.setObjectName("timelineSearch")
    mw._timeline_search.setPlaceholderText("搜索标题或标签…")
    mw._timeline_search.setClearButtonEnabled(True)
    mw._timeline_search.setFixedWidth(236)
    row.addWidget(mw._timeline_search)

    # 状态 chips（互斥，带计数）
    mw._timeline_status_chips = {}
    mw._status_chip_group = QButtonGroup(tools)
    mw._status_chip_group.setExclusive(True)
    for key, label, _status in STATUS_FILTERS:
        chip = QPushButton(label)
        chip.setObjectName("statusChip")
        chip.setCheckable(True)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        mw._status_chip_group.addButton(chip)
        row.addWidget(chip)
        mw._timeline_status_chips[key] = chip
    mw._timeline_status_chips["all"].setChecked(True)

    row.addStretch(1)

    # 排序
    mw._timeline_sort_combo = DropdownWidget()
    mw._timeline_sort_combo.setFixedWidth(combo_width(6))
    for key, label in TimelineModel.SORTS.items():
        mw._timeline_sort_combo.addItem(label, key)
    row.addWidget(mw._timeline_sort_combo)

    # 粒度分段控件（初值取设置里的「时间轴默认粒度」）
    mw._timeline_range_seg = SegmentedControl(TIMELINE_RANGES)
    mw._timeline_range_seg.set_current_value(mw._config.timeline_range)
    row.addWidget(mw._timeline_range_seg)

    return tools


# ----------------------------------------------------------------------
# 时间轴卡片 / 图例
# ----------------------------------------------------------------------


def _build_timeline_card(mw) -> QWidget:
    from ..timeline import TimelineController, TimelineTableView

    t = get_tokens()
    card = QFrame()
    card.setObjectName("timelineCard")
    card.setStyleSheet(
        f"QFrame#timelineCard {{ background: {t.surface_raised};"
        f" border: 1px solid {t.border_primary}; border-radius: 10px; }}"
    )

    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(1, 1, 1, 1)
    card_layout.setSpacing(0)

    mw._timeline_view = TimelineTableView()
    mw._timeline_ctl = TimelineController(
        mw._task_service,
        mw._timeline_view,
        selection=getattr(mw, "_selection", None),
        parent=mw,
    )
    card_layout.addWidget(mw._timeline_view, 1)
    return card


def _build_legend() -> QWidget:
    legend = QWidget()
    row = QHBoxLayout(legend)
    row.setContentsMargins(2, 0, 2, 0)
    row.setSpacing(16)

    for text in ("色条 = 起止区间（状态着色）", "填充 = 进度", "端点 = 截止"):
        label = QLabel(text)
        label.setObjectName("timelineLegend")
        row.addWidget(label)
    today = QLabel("│ = 今天")
    today.setObjectName("timelineLegendToday")
    row.addWidget(today)
    row.addStretch(1)
    hint = QLabel("单击选中 · 双击 / 右键打开维护 · 悬停查看详情")
    hint.setObjectName("timelineLegend")
    row.addWidget(hint)
    return legend


__all__ = ["STATUS_FILTERS", "TIMELINE_RANGES", "build"]
