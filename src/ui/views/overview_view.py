"""总览页（阶段 4）— 问候 + 快速新建 + 4 统计瓦片 + 焦点时间轴 + 近期活动 + 紧迫度分布。

数据全部来自 ``TaskService`` 的阶段 4 新接口（get_due_stats /
get_recent_activity / get_urgency_distribution），时间轴复用
``TimelineModel`` + ``TimelineTableView``。
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...models.task_status import TaskStatus
from ...utils.design_tokens import apply_display_font, get_tokens
from ...utils.signal_bus import get_signal_bus
from ..timeline import TimelineModel, TimelineTableView

#: 焦点时间轴 6 预设：(键, 显示名)
FOCUS_RANGES = (
    ("yesterday", "昨天"),
    ("today", "今天"),
    ("last_week", "上周"),
    ("week", "本周"),
    ("last_month", "上月"),
    ("month", "本月"),
)


class StatTile(QWidget):
    """可点击的统计瓦片。"""

    clicked = Signal()

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        # 原型 .tile{padding:13px 16px}——此前是 10/8，瓦片偏挤，「留白
        # 节奏」也是观感差距的一部分，这里对齐原型。
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(2)

        # 字号一律由 base.qss 的展示层字阶给出（#statTileValue 26px/800 等），
        # 此处只负责 objectName，不再就地写 font-size。
        self._label = QLabel(label)
        self._label.setObjectName("statTileLabel")
        self._value = QLabel("0")
        self._value.setObjectName("statTileValue")
        # 原型 .tile .num 带 tabular-nums；QSS 无此属性，必须用 QFont。
        apply_display_font(self._value, tabular=True)
        self._hint = QLabel("")
        self._hint.setObjectName("statTileHint")

        layout.addWidget(self._label)
        layout.addWidget(self._value)
        layout.addWidget(self._hint)

    def set_value(self, value: int, hint: str = "") -> None:
        self._value.setText(str(value))
        self._hint.setText(hint)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _greeting(now_hour: int) -> str:
    if now_hour < 6:
        return "凌晨好"
    if now_hour < 12:
        return "早上好"
    if now_hour < 18:
        return "下午好"
    return "晚上好"


class OverviewPage(QWidget):
    """总览页主体。"""

    task_requested = Signal(str)  # task_id：点击近期活动条目

    def __init__(self, task_service, config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("overviewPage")
        self._svc = task_service
        self._config = config
        self._partition_id: str | None = None
        self._range_key = "today"
        self._timeline_model = TimelineModel()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        layout.addWidget(self._build_greeting())
        layout.addWidget(self._build_tiles())
        layout.addWidget(self._build_focus_card(), 1)
        layout.addWidget(self._build_bottom_row())

        # 阶段 7 同款：总线事件 300ms 去抖
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.refresh)

        # 总线订阅只在此处建立一次。此前它写在 refresh_theme() 里，导致
        # ①主题未切换过时总览页完全不响应数据变化；②每次主题切换都重复连接，
        # 一次事件触发 N 次刷新。
        bus = get_signal_bus()
        for signal in (
            bus.task_created,
            bus.task_updated,
            bus.task_deleted,
            bus.task_status_changed,
            bus.batch_operation_completed,
            bus.archive_completed,
            bus.tasks_bulk_created,
        ):
            signal.connect(self._on_bus_event)

        from ...utils.theme_registry import register_theme_aware

        register_theme_aware(self)

    def refresh_theme(self) -> None:
        """主题切换：重算瓦片样式与时间轴配色。"""
        self.refresh()

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def _build_greeting(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(1)
        # 原型 .greet .g1{font:700 20px} / .greet .g2{font:400 11.5px var(--mono)}
        # ——副标题是**等宽**的（对齐时长的数字列），此前用的是 11px 正文体。
        self._greet_label = QLabel(_greeting(0))
        self._greet_label.setObjectName("greetTitle")
        apply_display_font(self._greet_label, tracking=0.2)
        self._greet_sub = QLabel("")
        self._greet_sub.setObjectName("greetSub")
        left.addWidget(self._greet_label)
        left.addWidget(self._greet_sub)
        row.addLayout(left)
        row.addStretch()

        self._quick_input = QLineEdit()
        self._quick_input.setObjectName("quickAdd")
        self._quick_input.setPlaceholderText("快速新建：- [ ] 修复登录 #前端 <2026-09-14>")
        self._quick_input.setFixedWidth(320)
        self._quick_input.returnPressed.connect(self._on_quick_add)
        row.addWidget(self._quick_input)

        add_btn = QPushButton("回车添加")
        add_btn.setObjectName("quickAddBtn")
        add_btn.clicked.connect(self._on_quick_add)
        row.addWidget(add_btn)
        return box

    def _build_tiles(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._tile_due = StatTile("今日到期")
        self._tile_over = StatTile("逾期")
        self._tile_doing = StatTile("进行中")
        self._tile_done = StatTile("本周完成")
        for tile in (self._tile_due, self._tile_over, self._tile_doing, self._tile_done):
            row.addWidget(tile, 1)
        self._tile_due.clicked.connect(lambda: self._goto_tasks("all"))
        self._tile_over.clicked.connect(lambda: self._goto_tasks("overdue"))
        self._tile_doing.clicked.connect(lambda: self._goto_tasks("doing"))
        self._tile_done.clicked.connect(lambda: self._goto_tasks("all"))
        return box

    def _build_focus_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("overviewCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("焦点时间轴")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        head.addWidget(title)
        head.addStretch()
        self._range_buttons: dict[str, QPushButton] = {}
        for key, label in FOCUS_RANGES:
            btn = QPushButton(label)
            btn.setObjectName("focusRangeBtn")
            btn.setCheckable(True)
            btn.setChecked(key == self._range_key)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=key: self.set_range(k))
            self._range_buttons[key] = btn
            head.addWidget(btn)
        box.addLayout(head)

        self._timeline = TimelineTableView()
        box.addWidget(self._timeline, 1)
        return card

    def _build_bottom_row(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        feed_card = QWidget()
        feed_card.setObjectName("overviewCard")
        feed_box = QVBoxLayout(feed_card)
        feed_box.setContentsMargins(10, 8, 10, 8)
        feed_box.setSpacing(4)
        feed_title = QLabel("近期活动")
        feed_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        feed_box.addWidget(feed_title)
        self._feed_layout = QVBoxLayout()
        self._feed_layout.setSpacing(2)
        feed_box.addLayout(self._feed_layout)
        feed_box.addStretch()
        row.addWidget(feed_card, 2)

        urg_card = QWidget()
        urg_card.setObjectName("overviewCard")
        urg_box = QVBoxLayout(urg_card)
        urg_box.setContentsMargins(10, 8, 10, 8)
        urg_box.setSpacing(4)
        urg_title = QLabel("紧迫度分布")
        urg_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        urg_box.addWidget(urg_title)
        self._urgency_bars: dict[int, QProgressBar] = {}
        for level, name in ((0, "紧急"), (1, "重要"), (2, "关注"), (3, "普通")):
            line = QHBoxLayout()
            label = QLabel(name)
            label.setFixedWidth(32)
            label.setStyleSheet("font-size: 11px;")
            bar = QProgressBar()
            bar.setObjectName("urgencyBar")
            bar.setTextVisible(True)
            bar.setFixedHeight(14)
            self._urgency_bars[level] = bar
            line.addWidget(label)
            line.addWidget(bar, 1)
            urg_box.addLayout(line)
        urg_box.addStretch()
        row.addWidget(urg_card, 1)
        return box

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------

    def set_range(self, range_key: str) -> None:
        self._range_key = range_key
        for key, btn in self._range_buttons.items():
            btn.setChecked(key == range_key)
        self._refresh_timeline()

    @property
    def range_key(self) -> str:
        return self._range_key

    def set_partition(self, partition_id: str | None) -> None:
        self._partition_id = partition_id or None

    def _goto_tasks(self, filter_key: str) -> None:
        """瓦片点击 → 切换任务页（筛选交给时间轴的工具行）。"""
        window = self.window()
        if hasattr(window, "_switch_view"):
            window._switch_view("tasks")
        ctl = getattr(window, "_timeline_ctl", None)
        if ctl is not None and filter_key != "all":
            if filter_key == "overdue":
                ctl.set_filters(statuses={TaskStatus.OVERDUE})
            elif filter_key == "doing":
                ctl.set_filters(statuses={TaskStatus.DOING})

    def _on_quick_add(self) -> None:
        text = self._quick_input.text().strip()
        if not text:
            return
        try:
            self._svc.create_task(text, partition_id=self._partition_id or "")
        except ValueError:
            return
        self._quick_input.clear()
        self.refresh()

    def _on_bus_event(self, *_args) -> None:
        self._timer.start()

    def flush_pending_refresh(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.refresh()

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        pid = self._partition_id
        name_map = self._svc.get_partition_name_map()
        pname = name_map.get(pid or "", "全部分区")

        today = date.today()
        weekday = "一二三四五六日"[today.isoweekday() - 1]
        tasks = self._scoped_tasks(pid)

        self._greet_label.setText(f"{_greeting(datetime.now().hour)}")
        self._greet_sub.setText(
            f"{today.isoformat()} · 周{weekday} · {pname} · "
            f"{sum(1 for t in tasks if not t.archived)} 个待处理"
        )

        stats = self._svc.get_due_stats(pid)
        self._tile_due.set_value(stats["due_today"], "今天截止")
        self._tile_over.set_value(stats["overdue"], "点击查看")
        self._tile_doing.set_value(stats["doing"], "进行中")
        self._tile_done.set_value(stats["done_this_week"], "本周完成")

        self._refresh_feed(pid)
        self._refresh_urgency(pid)
        self._refresh_timeline(tasks)

    def _scoped_tasks(self, pid: str | None) -> list:
        """当前分区下的全部任务（含已归档），供问候语与焦点时间轴复用。"""
        tasks = self._svc.get_all()
        if pid:
            tasks = [t for t in tasks if t.partition_id == pid]
        return tasks

    def _refresh_timeline(self, tasks: list | None = None) -> None:
        """焦点时间轴：与任务页口径一致（包含已完成 / 已归档任务）。

        分区 ``archive_days=0`` 时「完成即归档」，若这里排除归档，勾选完成
        后色条会从总览页消失，与任务页的表现不一致。
        """
        if tasks is None:
            tasks = self._scoped_tasks(self._partition_id)
        data = self._timeline_model.build(
            tasks, self._range_key, include_archived=True
        )
        self._timeline.set_timeline(data)

    def _refresh_feed(self, pid: str | None) -> None:
        while self._feed_layout.count():
            item = self._feed_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        entries = self._svc.get_recent_activity(limit=8, partition_id=pid)
        t = get_tokens()
        if not entries:
            hint = QLabel("暂无活动记录")
            hint.setStyleSheet(f"font-size: 11px; color: {t.text_secondary};")
            self._feed_layout.addWidget(hint)
            return
        for entry in entries:
            ts = str(entry.get("ts", ""))[:16].replace("T", " ")
            label = QLabel(f"{ts}　{entry.get('title', '')}　{entry.get('content', '')}")
            label.setStyleSheet(f"font-size: 11px; color: {t.text_secondary};")
            label.setWordWrap(False)
            self._feed_layout.addWidget(label)

    def _refresh_urgency(self, pid: str | None) -> None:
        dist = self._svc.get_urgency_distribution(pid)
        total = sum(dist.values())
        for level, bar in self._urgency_bars.items():
            value = dist.get(level, 0)
            bar.setMaximum(max(1, total))
            bar.setValue(value)
            bar.setFormat(f"{value}")


def build(mw) -> QWidget:
    """页面工厂：注册表中 ``overview`` 入口。"""
    page = OverviewPage(mw._task_service, mw._config, parent=None)
    page.set_partition(mw._partition_ctrl.active_id or None)
    mw._overview_page = page
    page.task_requested.connect(mw._on_graph_task_activated)
    return page
