"""时间轴（甘特）视图包 — 阶段 3 任务页内核。

- 纯数据布局：:class:`TimelineModel` / :class:`TimelineData` / :class:`TimelineRow`
- Qt 视图层：:class:`TimelineTableView` / :class:`TimelineTableModel` /
  :class:`TimelineGanttDelegate`
- 编排：:class:`TimelineController`（TaskService ↔ 视图 ↔ SelectionContext）
"""

from .timeline_controller import TimelineController  # noqa: F401
from .timeline_gantt import (  # noqa: F401
    HEADER_HEIGHT,
    ROW_HEIGHT,
    TITLE_COL_WIDTH,
    TimelineGanttDelegate,
    TimelineTableModel,
    TimelineTableView,
    axis_cell_width,
)
from .timeline_model import (  # noqa: F401
    RANGE_KEYS,
    TimelineData,
    TimelineModel,
    TimelineRow,
    resolve_range,
)
