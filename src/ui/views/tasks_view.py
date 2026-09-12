"""任务页（page0）构建 — 纯移动自 MainWindow._setup_central_widget（Phase 1）。

TODO(phase3): 时间轴视图替换本页；此过渡期保持与旧实现逐行一致。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...utils.widget_utils import combo_width
from ..calendar_heatmap.calendar_heatmap_widget import CalendarHeatmapWidget
from ..task_list.batch_toolbar import BatchToolbar
from ..task_list.task_edit_panel import TaskEditPanel
from ..task_list.task_list_model import COL_ARCHIVED, TaskListModel
from ..task_list.task_list_view import TaskListView
from ..widgets.calendar_popup import CalendarPopup  # noqa: F401  (moved import)
from ..widgets.dropdown import DropdownWidget
from ..widgets.filter_bar import FilterBar
from ..widgets.progress_dynamics_bar import ProgressDynamicsBar
from ..widgets.quick_overview_bar import QuickOverviewBar
from ..widgets.status_badge_strip import StatusBadgeStrip


def build(mw) -> QWidget:
    """Build the task page exactly as MainWindow._setup_central_widget did."""
    task_page = QWidget()
    task_layout = QVBoxLayout(task_page)
    task_layout.setContentsMargins(8, 4, 8, 4)
    task_layout.setSpacing(2)

    # Row 1: QuickOverviewBar only (presets + carousel)
    mw._top_bar = QWidget()
    top_bar_layout = QHBoxLayout(mw._top_bar)
    top_bar_layout.setContentsMargins(4, 0, 4, 0)
    top_bar_layout.setSpacing(0)

    mw._quick_overview = QuickOverviewBar(
        mw._repository, max_items=2, group_size=2, interval_seconds=5
    )
    mw._quick_overview.preset_activated.connect(mw._on_quick_preset)
    mw._quick_overview.task_clicked.connect(mw._on_carousel_clicked)
    top_bar_layout.addWidget(mw._quick_overview, 1)
    task_layout.addWidget(mw._top_bar)

    # Heatmap widget (created here, used in heatmap page)
    mw._heatmap_widget = CalendarHeatmapWidget(mw._repository, mw._config)
    mw._heatmap_widget.back_requested.connect(lambda: mw._switch_view("edit"))

    # Row 2: FilterBar + StatusBadgeStrip (same row, StatusBadgeStrip right-aligned)
    filter_row = QWidget()
    filter_row_layout = QHBoxLayout(filter_row)
    filter_row_layout.setContentsMargins(4, 0, 4, 0)
    filter_row_layout.setSpacing(6)

    mw._filter_bar = FilterBar()
    mw._filter_bar.set_sort(mw._config.default_sort)
    filter_row_layout.addWidget(mw._filter_bar, 1)

    mw._status_badge = StatusBadgeStrip(mw._repository)
    mw._status_badge.filter_changed.connect(mw._on_filter_changed)
    filter_row_layout.addWidget(mw._status_badge)
    task_layout.addWidget(filter_row)

    # Splitter: task list (left) + edit panel (right)
    mw._splitter_container = QWidget()
    mw._splitter_stack = QStackedLayout(mw._splitter_container)
    mw._splitter_stack.setContentsMargins(0, 0, 0, 0)
    mw._splitter_stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

    mw._splitter = QSplitter(Qt.Orientation.Horizontal)
    mw._splitter.setHandleWidth(2)
    mw._splitter.setChildrenCollapsible(False)
    mw._splitter.setStretchFactor(0, 1)
    mw._splitter.setStretchFactor(1, 1)

    # === Left panel: BatchToolbar + TaskListView + Pagination ===
    left_panel = QWidget()
    left_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    left_layout = QVBoxLayout(left_panel)
    left_layout.setContentsMargins(0, 0, 2, 0)
    left_layout.setSpacing(2)

    mw._batch_toolbar = BatchToolbar()
    left_layout.addWidget(mw._batch_toolbar)

    mw._task_model = TaskListModel()
    mw._task_view = TaskListView(
        mw._repository,
        task_service=mw._task_service,
    )
    mw._task_view.set_model(mw._task_model)
    mw._task_view.setColumnHidden(COL_ARCHIVED, True)  # 归档列仅管理视图可见
    mw._task_view.task_selected.connect(mw._on_view_task_selected)
    mw._task_view.detail_requested.connect(mw._on_detail_requested)
    # Batch operations from right-click menu
    mw._task_view.batch_status_change.connect(mw._on_batch_status_change)
    mw._task_view.batch_urgency_change.connect(mw._on_batch_urgency_change)
    mw._task_view.batch_delete.connect(mw._on_batch_delete)
    mw._task_view.batch_suspend.connect(mw._on_batch_suspend)
    mw._task_view.batch_restart.connect(mw._on_batch_restart)
    mw._task_view.batch_postpone.connect(mw._on_batch_postpone)
    mw._task_view.batch_move_partition.connect(mw._on_batch_move_partition)
    left_layout.addWidget(mw._task_view, 1)

    # Pagination
    page_widget = QWidget()
    page_row = QHBoxLayout(page_widget)
    page_row.setContentsMargins(4, 2, 4, 2)
    page_row.setSpacing(4)
    page_row.addStretch()
    mw._prev_page_btn = QPushButton("‹")
    mw._prev_page_btn.setObjectName("navBtn")
    mw._prev_page_btn.setFixedWidth(28)
    mw._prev_page_btn.clicked.connect(mw._on_page_prev)
    page_row.addWidget(mw._prev_page_btn)
    mw._page_label = QLabel("1 / 1")
    mw._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    page_row.addWidget(mw._page_label)
    mw._next_page_btn = QPushButton("›")
    mw._next_page_btn.setObjectName("navBtn")
    mw._next_page_btn.setFixedWidth(28)
    mw._next_page_btn.clicked.connect(mw._on_page_next)
    page_row.addWidget(mw._next_page_btn)
    mw._page_size_combo = DropdownWidget()
    mw._page_size_combo.setFixedWidth(combo_width(4))
    for n in ["20", "50", "100"]:
        mw._page_size_combo.addItem(n, int(n))
    mw._page_size_combo.setCurrentText(str(mw._page_size))
    mw._page_size_combo.currentIndexChanged.connect(mw._on_page_size_changed)
    page_row.addWidget(mw._page_size_combo)
    left_layout.addWidget(page_widget)

    mw._splitter.addWidget(left_panel)

    # === Right panel: ProgressDynamicsBar + TaskEditPanel ===
    right_panel = QWidget()
    right_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(2, 0, 0, 0)
    right_layout.setSpacing(2)

    mw._progress_bar = ProgressDynamicsBar(mw._repository)
    right_layout.addWidget(mw._progress_bar)
    mw._progress_bar.progress_filter_activated.connect(mw._on_progress_filter)
    mw._progress_bar.task_clicked.connect(mw._on_carousel_clicked)

    mw._edit_panel = TaskEditPanel(
        mw._repository,
        mw._task_model,
        task_service=mw._task_service,
    )
    right_layout.addWidget(mw._edit_panel, 1)
    mw._splitter.addWidget(right_panel)

    mw._splitter_stack.addWidget(mw._splitter)
    # Password mask overlay
    mw._partition_mask = QWidget()
    mw._partition_mask.setObjectName("partitionMask")
    mask_layout = QVBoxLayout(mw._partition_mask)
    mask_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mask_hint = QLabel("此分区已加密\n请输入密码查看内容")
    mask_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mask_hint.setStyleSheet(
        "QLabel { font-size: 16px; font-weight: bold;" " background: transparent; border: none; }"
    )
    mask_layout.addWidget(mask_hint)
    unlock_btn = QPushButton("输入密码解锁")
    unlock_btn.setObjectName("saveBtn")
    unlock_btn.setFixedWidth(140)
    # Deferred connect: _partition_ctrl created after _setup_central_widget
    unlock_btn.clicked.connect(lambda: mw._partition_ctrl.unlock())
    mask_btn_row = QHBoxLayout()
    mask_btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mask_btn_row.addWidget(unlock_btn)
    mask_layout.addLayout(mask_btn_row)
    mw._splitter_stack.addWidget(mw._partition_mask)
    mw._splitter_stack.setCurrentIndex(0)
    task_layout.addWidget(mw._splitter_container, 1)

    return task_page
