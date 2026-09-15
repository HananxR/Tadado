"""SettingsDrawer —— 设置面板（右侧滑入抽屉，对齐原型 ``#setDrawer``）。

原型里「设置」**不是模态对话框**，而是与维护抽屉共用同一个 ``.drawer`` 外壳、
宽度 420px 的右侧滑入面板：

.. code-block:: html

    <div class="drawer" id="setDrawer" style="width:420px">
      <div class="dr-h">
        <span class="t">设置</span>
        <div class="seg" id="setTabs">常规 / AI 助手 / 分区 / 关于</div>
        <button class="icon-btn" id="setClose">✕</button>
      </div>
      <div class="dr-b">
        <div class="set-sec"><div class="set-sec-t">外观</div>
          <div class="set-row"><span>主题</span><div class="seg">…</div></div>
        </div>
      </div>
    </div>

与旧 ``SettingsDialog`` 的三条关键差异：

1. **页签搬到头部**（``.dr-h`` 中间槽的分段控件），内容区不再有 QTabWidget。
2. **没有确认 / 取消**——每项改完立即落盘并广播 ``config_changed``，
   与原型「开关一动即生效」的交互一致。
3. 行样式走 ``.set-row``（左标签 / 右控件 / 底部 1px 分隔线），
   开关用 :class:`ToggleSwitch`，枚举用 :class:`SegmentedControl`，
   数值 / 路径用 ``.mono`` 等宽标签。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...services.task_service import TaskService
from ...utils.design_tokens import expand_qss, get_tokens
from ...utils.signal_bus import get_signal_bus
from ..widgets.segmented_control import SegmentedControl
from ..widgets.toggle_switch import ToggleSwitch
from .side_drawer import SideDrawer

_log = logging.getLogger("runlog")

#: 原型 ``style="width:420px"``
SETTINGS_WIDTH = 420
#: 归档阈值「永不归档」哨兵值（与库内约定一致）
ARCHIVE_NEVER = 9999

#: 页签 (key, 标题)，顺序即头部顺序
TABS = (
    ("gen", "常规"),
    ("ai", "AI 助手"),
    ("part", "分区"),
    ("about", "关于"),
)

#: 抽屉内容样式（原型 ``.set-sec`` / ``.set-row`` / ``.sw`` / ``.mono``）。
#: 走 ``expand_qss``，``{{token}}`` 由当前主题解析，切主题无需重建。
_CONTENT_QSS = """
QLabel#setSecTitle {
    font-size: 10.5px; font-weight: 500; letter-spacing: 1px;
    color: {{text_disabled}};
}
QFrame#setRow {
    background: transparent;
    border-bottom: 1px solid {{border_primary}};
}
QFrame#setRowLast {
    background: transparent;
    border-bottom: none;
}
QLabel#setRowLabel { font-size: 12.5px; color: {{text_primary}}; }
QLabel#setRowValue { font-size: 11.5px; color: {{text_secondary}}; }
QLabel#setMono     { font-family: {{font_mono}}; font-size: 11px; color: {{text_secondary}}; }
QLabel#setMonoStrong { font-family: {{font_mono}}; font-size: 11px; color: {{text_primary}}; }
QLabel#setHint     { font-size: 10.5px; color: {{text_disabled}}; }
QLabel#setSectionHint { font-size: 11px; color: {{text_secondary}}; }
QLabel#setMonoHint { font-family: {{font_mono}}; font-size: 10.5px; color: {{text_secondary}}; }

QPushButton#setGhostBtn {
    font-size: 11px; padding: 4px 12px; border-radius: 8px;
    border: 1px solid {{border_2}}; background: {{surface}};
    color: {{text_primary}};
}
QPushButton#setGhostBtn:hover {
    border-color: {{accent}}; color: {{accent}}; background: {{hover}};
}

QPushButton#setPrimaryBtn {
    font-size: 11.5px; padding: 5px 14px; border-radius: 8px;
    border: 1px solid {{accent}}; background: {{accent}}; color: {{text_on_accent}};
}
QPushButton#setPrimaryBtn:hover {
    background: {{accent_hover}}; border-color: {{accent_hover}};
}

QPushButton#setManageBtn {
    font-size: 11px; padding: 4px 12px; border-radius: 8px;
    border: 1px solid {{border_2}}; background: {{surface}};
    color: {{accent}};
}
QPushButton#setManageBtn:hover {
    border-color: {{accent}}; background: {{hover}};
}

QFrame#setCard {
    background: {{surface_raised}};
    border: 1px solid {{border_primary}};
    border-radius: 10px;
}
"""


class _WrapLabel(QLabel):
    """``wordWrap`` 的 QLabel 会把「最长不可断词」当成最小宽度。

    中文长句与磁盘路径都没有空格，整行会被视为**一个词**，从而把所在的
    ``QStackedWidget``（取所有页的最大值）撑到 600px 以上，把 420px 的
    抽屉内容横向裁掉。QLabel 内部换行用的是
    ``QTextOption::WrapAtWordBoundaryOrAnywhere``，本就能在任意字符断开，
    所以只需把最小宽度放宽即可。
    """

    #: 允许压缩到的最小宽度（够放一个中文词 + 省略号）
    MIN_W = 96

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = super().minimumSizeHint()
        if self.wordWrap():
            return QSize(min(hint.width(), self.MIN_W), hint.height())
        return hint


class SettingsDrawer(SideDrawer):
    """设置抽屉：头部页签 + 即时生效的配置行。

    由 :class:`~src.ui.main_window.MainWindow` 惰性创建并常驻内存；
    :meth:`on_before_open` 会在每次滑入前重新读取分区表 / AI / Skill 状态。
    """

    def __init__(
        self,
        config: AppConfig,
        task_service: TaskService,
        update_checker=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, width=SETTINGS_WIDTH, title="设置")
        self._config = config
        self._task_service = task_service
        self._update_checker = update_checker
        self._partitions_data: list[dict] = []
        self._bus = get_signal_bus()
        self._pages: dict[str, QWidget] = {}

        # ── 头部页签（原型 .dr-h 里的 #setTabs）──
        self._tab_seg = SegmentedControl([(label, key) for key, label in TABS])
        self._tab_seg.changed.connect(self._on_tab_changed)
        self.add_header_widget(self._tab_seg)

        # ── 内容区（原型 .dr-b，逐个页签叠放）──
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self.body_layout.addWidget(self._stack)

        self._pages = {
            "gen": self._build_general(),
            "ai": self._build_ai(),
            "part": self._build_partition(),
            "about": self._build_about(),
        }
        for key, _label in TABS:
            self._stack.addWidget(self._pages[key])

        self.refresh_theme()

    # ==================================================================
    # 通用构件（对应原型 .set-sec / .set-row）
    # ==================================================================

    def _section(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        """新建一个 ``.set-sec`` 分组；返回 (部件, 用于追加行的布局)。"""
        holder = QWidget()
        outer = QVBoxLayout(holder)
        outer.setContentsMargins(0, 0, 0, 18)
        outer.setSpacing(0)
        head = QLabel(title)
        head.setObjectName("setSecTitle")
        outer.addWidget(head)
        return holder, outer

    def _row(
        self, label: str, *controls: QWidget, last: bool = False, hint: str = ""
    ) -> QFrame:
        """一行 ``.set-row``：左标签（+可选灰色说明），右侧按 8px 间隔排控件。"""
        row = QFrame()
        row.setObjectName("setRowLast" if last else "setRow")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 7, 0, 7)
        lay.setSpacing(8)
        name = QLabel(label)
        name.setObjectName("setRowLabel")
        lay.addWidget(name)
        if hint:
            note = QLabel(hint)
            note.setObjectName("setHint")
            lay.addWidget(note)
        lay.addStretch(1)
        for widget in controls:
            lay.addWidget(widget)
        return row

    def _mono(self, text: str, *, strong: bool = False) -> QLabel:
        """等宽数值（热键 / 时刻 / 天数）。

        刻意**不**折行：这些都是短值，折行只会让右侧列变成两行。
        长文本（Skill 路径、AI 状态）走 :meth:`_hint`。
        """
        label = QLabel(text)
        label.setObjectName("setMonoStrong" if strong else "setMono")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _hint(self, text: str, *, wrap: bool = True, name: str = "setHint") -> QLabel:
        label = _WrapLabel(text)
        label.setObjectName(name)
        label.setWordWrap(wrap)
        return label

    def _button(
        self, text: str, *, kind: str = "ghost", on_click=None
    ) -> QPushButton:
        """``kind`` ∈ {ghost, primary, manage}，对应三种原型按钮样式。"""
        names = {
            "ghost": "setGhostBtn",
            "primary": "setPrimaryBtn",
            "manage": "setManageBtn",
        }
        btn = QPushButton(text)
        btn.setObjectName(names[kind])
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if on_click is not None:
            btn.clicked.connect(on_click)
        return btn

    def _switch(self, checked: bool, on_change) -> ToggleSwitch:
        """先回填再连接，避免构造期把默认值写回磁盘。"""
        sw = ToggleSwitch()
        sw.setChecked(bool(checked))
        sw.toggled.connect(on_change)
        return sw

    # ==================================================================
    # 页签一：常规
    # ==================================================================

    def _build_general(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 外观（原型 setTheme：亮色 / 暗色 / 跟随系统）──
        sec, body = self._section("外观")
        self._theme_seg = SegmentedControl(
            [("亮色", "light"), ("暗色", "dark"), ("跟随系统", "system")]
        )
        self._theme_seg.set_current_value(self._config.theme_mode)
        self._theme_seg.changed.connect(self._on_theme_changed)
        body.addWidget(self._row("主题", self._theme_seg, last=True))
        layout.addWidget(sec)

        # ── 唤起与常驻 ──
        sec, body = self._section("唤起与常驻")
        self._hotkey_label = self._mono("", strong=True)
        body.addWidget(
            self._row(
                "全局热键",
                self._hotkey_label,
                self._button("修改", on_click=self._on_edit_hotkey),
            )
        )
        body.addWidget(
            self._row(
                "常驻置顶",
                self._switch(
                    self._config.get("general", "pin_on_top", default=False),
                    self._on_pin_toggled,
                ),
            )
        )
        body.addWidget(
            self._row(
                "最小化到托盘",
                self._switch(self._config.minimize_to_tray, self._on_tray_toggled),
            )
        )
        body.addWidget(
            self._row(
                "开机自启动",
                self._switch(self._config.auto_start, self._on_autostart_toggled),
                last=True,
            )
        )
        layout.addWidget(sec)

        # ── 任务视图（原型 setRange / setBottom / setAutoClose）──
        sec, body = self._section("任务视图")
        self._range_seg = SegmentedControl(
            [("本周", "week"), ("本月", "month"), ("近 30 天", "30d")]
        )
        self._range_seg.set_current_value(self._config.timeline_range)
        self._range_seg.changed.connect(self._on_range_changed)
        body.addWidget(self._row("时间轴默认粒度", self._range_seg))

        body.addWidget(
            self._row(
                "已完成任务置底",
                self._switch(
                    self._config.sort_completed_last, self._on_completed_last_toggled
                ),
            )
        )
        body.addWidget(
            self._row(
                "保存后自动收起抽屉",
                self._switch(
                    self._config.auto_collapse_drawer, self._on_auto_collapse_toggled
                ),
                last=True,
            )
        )
        layout.addWidget(sec)

        # ── 自动化 ──
        sec, body = self._section("自动化")
        body.addWidget(
            self._row(
                "自动归档",
                self._switch(self._config.archive_enabled, self._on_archive_toggled),
                hint="按分区阈值",
            )
        )
        self._archive_days_label = self._mono("")
        body.addWidget(
            self._row(
                "归档阈值（天）",
                self._archive_days_label,
                hint="当前分区",
            )
        )
        body.addWidget(
            self._row(
                "每日摘要", self._mono(self._config.reminder_daily_digest_time)
            )
        )
        quiet = (
            f"{self._config.get('reminders', 'quiet_hours_start', default='22:00')}"
            f" – {self._config.get('reminders', 'quiet_hours_end', default='08:00')}"
        )
        body.addWidget(self._row("安静时段", self._mono(str(quiet))))
        body.addWidget(
            self._row(
                "逾期自动标记",
                self._switch(
                    self._config.reminders_enabled, self._on_reminders_toggled
                ),
                last=True,
            )
        )
        layout.addWidget(sec)

        layout.addStretch(1)
        return page

    # ==================================================================
    # 页签二：AI 助手
    # ==================================================================

    def _build_ai(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 助手（原型 setProvider / setResume / setUsage / setEnv）──
        sec, body = self._section("助手")
        # 标签用厂商名而非产品全称：420px 抽屉里 "Claude Code" 会把分段控件
        # 撑到 320px 加上左侧标签后超出可用宽度，被 body 裁掉
        self._provider_seg = SegmentedControl(
            [("Claude", "claude"), ("Codex", "codex"), ("自动检测", "")]
        )
        self._provider_seg.set_current_value(
            self._config.get("ai_assistant", "provider") or ""
        )
        self._provider_seg.changed.connect(self._on_provider_changed)
        body.addWidget(self._row("助手提供商", self._provider_seg))

        # 可用性状态：即时检测，不必等托盘里点一下才发现命令找不到
        self._ai_status = self._hint("", wrap=True, name="setSectionHint")
        status_row = QFrame()
        status_row.setObjectName("setRow")
        status_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sl = QVBoxLayout(status_row)
        sl.setContentsMargins(0, 0, 0, 8)
        sl.setSpacing(0)
        sl.addWidget(self._ai_status)
        body.addWidget(status_row)

        self._ai_workspace = self._mono("")
        body.addWidget(
            self._row(
                "专用工作区",
                self._button("打开", on_click=self._on_open_workspace),
            )
        )
        body.addWidget(
            self._row(
                "自动续接上次会话",
                self._switch(
                    bool(self._config.get("ai_assistant", "resume", default=True)),
                    lambda v: self._set_ai_flag("resume", v),
                ),
            )
        )
        body.addWidget(
            self._row(
                "会话用量超 80% 提醒",
                self._switch(
                    bool(self._config.get("ai_assistant", "usage_alert", default=True)),
                    lambda v: self._set_ai_flag("usage_alert", v),
                ),
            )
        )
        body.addWidget(
            self._row(
                "注入分区环境变量",
                self._switch(
                    bool(self._config.get("ai_assistant", "inject_env", default=True)),
                    lambda v: self._set_ai_flag("inject_env", v),
                ),
                last=True,
            )
        )
        layout.addWidget(sec)

        # ── Skill 管理（原型 setSkillCard）──
        sec, body = self._section("Skill 管理")
        card = QFrame()
        card.setObjectName("setCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)
        self._skill_path = self._hint("", name="setMonoHint")
        cl.addWidget(self._skill_path)

        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(8)
        edit_btn = self._button("编辑 Skill", on_click=self._on_edit_skill)
        edit_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btns.addWidget(edit_btn)
        sync_btn = self._button(
            "同步到宿主目录", kind="primary", on_click=self._on_sync_skill
        )
        sync_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btns.addWidget(sync_btn)
        cl.addLayout(btns)
        body.addWidget(card)
        body.addWidget(
            self._row(
                "",
                self._hint(
                    "resources/skill/tadado/SKILL.md 为唯一权威源（带 version 字段）"
                ),
                last=True,
            )
        )
        layout.addWidget(sec)

        layout.addStretch(1)
        return page

    def _set_ai_flag(self, key: str, value) -> None:
        """三个 AI 开关共用：写回配置后让托盘/启动逻辑自行读取生效。"""
        self._config.set("ai_assistant", key, value=bool(value))
        self._apply()

    def _on_open_workspace(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from ...services.ai_assistant import _workspace_dir

        path = _workspace_dir(self._config)
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ==================================================================
    # 页签三：分区
    # ==================================================================

    def _build_partition(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sec, body = self._section("分区管理")
        self._partition_list = QWidget()
        self._partition_list_layout = QVBoxLayout(self._partition_list)
        self._partition_list_layout.setContentsMargins(0, 0, 0, 0)
        self._partition_list_layout.setSpacing(0)
        body.addWidget(self._partition_list)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 10, 0, 0)
        add_row.addWidget(
            self._button("+ 新增分区", kind="primary", on_click=self._on_add_partition)
        )
        add_row.addStretch(1)
        body.addLayout(add_row)
        layout.addWidget(sec)

        hint_sec, hint_body = self._section("归档")
        hint_body.addWidget(
            self._hint(
                "「归档阈值」指任务完成多少天后自动移入归档；阈值与锁定时长按分区独立配置。"
                "点击各分区右侧的「管理」可调整名称、阈值、自动锁定与密码。"
            )
        )
        layout.addWidget(hint_sec)

        layout.addStretch(1)
        return page

    def _populate_partitions(self) -> None:
        """重建分区行：``名称 | 无密码 · 归档 N 天 | [管理]``。"""
        while self._partition_list_layout.count():
            item = self._partition_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        try:
            self._partitions_data = self._task_service.get_all_partitions()
        except Exception:  # pragma: no cover - 服务异常时保持空列表
            _log.exception("加载分区列表失败")
            self._partitions_data = []

        if not self._partitions_data:
            self._partition_list_layout.addWidget(self._hint("暂无分区"))
            self._archive_days_label.setText("—")
            return

        active_id = self._active_partition_id()
        total = len(self._partitions_data)
        active = next((p for p in self._partitions_data if p["id"] == active_id), None)
        if active is None:
            self._archive_days_label.setText("—")
        else:
            active_days = int(active.get("archive_days", 0) or 0)
            self._archive_days_label.setText(
                "永不" if active_days >= ARCHIVE_NEVER else str(active_days)
            )
        for idx, p in enumerate(self._partitions_data):
            pid = p["id"]
            days = int(p.get("archive_days", 0) or 0)
            if not int(p.get("archive_enabled", 1) or 0):
                archive = "归档关闭"
            elif days >= ARCHIVE_NEVER:
                archive = "永不归档"
            else:
                archive = f"归档 {days} 天"

            meta = "有密码" if p.get("password") else "无密码"
            meta = f"{meta} · {archive}"
            if pid == active_id:
                meta = f"{meta} · 当前分区"

            row = self._row(
                p["name"],
                self._mono(meta),
                self._button("管理", kind="manage", on_click=self._make_manage(pid)),
                last=idx == total - 1,
            )
            self._partition_list_layout.addWidget(row)

    def _make_manage(self, partition_id: str):
        """为「管理」按钮生成回调（闭包绑定到具体分区，避免循环变量捕获问题）。"""

        def _handler() -> None:
            target = next(
                (p for p in self._partitions_data if p["id"] == partition_id), None
            )
            if target is not None:
                self._on_manage_partition(target)

        return _handler

    def _active_partition_id(self) -> str:
        ctrl = getattr(self.window(), "_partition_ctrl", None)
        return getattr(ctrl, "active_id", "") or ""

    def _on_add_partition(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "新增分区", "分区名称：")
        name = (name or "").strip()
        if not ok or not name:
            return
        if any(p["name"] == name for p in self._partitions_data):
            QMessageBox.warning(self, "名称重复", f'分区「{name}」已存在，请换一个名称。')
            return
        created = self._task_service.upsert_partition(name)
        _log.info("Partition created via settings drawer: %s id=%s", name, created["id"])
        self._partitions_data = self._task_service.get_all_partitions()
        self._populate_partitions()
        self._bus.partitions_changed.emit()

    def _on_manage_partition(self, partition: dict) -> None:
        dlg = _PartitionDialog(
            self._task_service, self._config, partition, parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._populate_partitions()
            self._bus.partitions_changed.emit()

    # ==================================================================
    # 页签四：关于
    # ==================================================================

    def _build_about(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from ..dialogs.about_dialog import AboutPage

        layout.addWidget(AboutPage(update_checker=self._update_checker))
        layout.addStretch(1)
        return page

    # ==================================================================
    # 打开前刷新
    # ==================================================================

    def on_before_open(self) -> None:
        """每次滑入前重新读取配置与动态内容（分区 / AI / Skill）。"""
        self._theme_seg.set_current_value(self._config.theme_mode)
        self._hotkey_label.setText(self._hotkey_text())
        self._range_seg.set_current_value(self._config.timeline_range)
        self._provider_seg.set_current_value(
            self._config.get("ai_assistant", "provider") or ""
        )
        self._populate_partitions()
        self._refresh_ai_status()
        self._refresh_skill_status()
        self._scroll.verticalScrollBar().setValue(0)

    def _on_tab_changed(self, key) -> None:
        page = self._pages.get(str(key))
        if page is not None:
            self._stack.setCurrentWidget(page)
            self._scroll.verticalScrollBar().setValue(0)

    # ==================================================================
    # 配置写入（即时生效）
    # ==================================================================

    def _apply(self) -> None:
        """落盘并广播 ``config_changed``——主题刷新等联动都挂在它上面。"""
        self._config.save()
        self._bus.config_changed.emit()

    def _on_theme_changed(self, value) -> None:
        if not value:
            return
        self._config.set("display", "theme", value=value)
        self._apply()

    def _on_pin_toggled(self, checked: bool) -> None:
        self._config.set("general", "pin_on_top", value=bool(checked))
        self._apply()
        # 立即作用到窗口，并让标题栏按钮跟随
        shell = getattr(self.window(), "_window_shell", None)
        if shell is not None:
            shell.set_pinned(bool(checked))
        pin_btn = getattr(self.window(), "_pin_btn", None)
        if pin_btn is not None and pin_btn.isChecked() != bool(checked):
            pin_btn.blockSignals(True)
            pin_btn.setChecked(bool(checked))
            pin_btn.blockSignals(False)

    def _on_tray_toggled(self, checked: bool) -> None:
        self._config.set("general", "minimize_to_tray", value=bool(checked))
        self._apply()

    def _on_autostart_toggled(self, checked: bool) -> None:
        from ...utils.win32_autostart import set_autostart

        self._config.set("general", "auto_start", value=bool(checked))
        set_autostart(bool(checked))
        self._apply()

    def _on_range_changed(self, value) -> None:
        if not value:
            return
        self._config.set("general", "timeline_range", value=value)
        self._apply()

    def _on_auto_collapse_toggled(self, checked: bool) -> None:
        self._config.set("general", "auto_collapse_drawer", value=bool(checked))
        self._apply()

    def _on_completed_last_toggled(self, checked: bool) -> None:
        self._config.set("general", "sort_completed_last", value=bool(checked))
        self._apply()

    def _on_archive_toggled(self, checked: bool) -> None:
        self._config.set("archive", "enabled", value=bool(checked))
        self._apply()

    def _on_reminders_toggled(self, checked: bool) -> None:
        self._config.set("reminders", "enabled", value=bool(checked))
        self._apply()

    def _on_provider_changed(self, value) -> None:
        self._config.set("ai_assistant", "provider", value=value or "")
        self._apply()
        self._refresh_ai_status()

    # ==================================================================
    # 全局热键
    # ==================================================================

    def _hotkey_text(self) -> str:
        value = str(self._config.get("general", "hotkey", default="") or "")
        return value or "未设置"

    def _on_edit_hotkey(self) -> None:
        """校验后写回；非法组合直接拒绝，避免配置里留下注册不上的热键。"""
        from PySide6.QtWidgets import QInputDialog

        from ...utils import win32_hotkey

        current = str(self._config.get("general", "hotkey", default="") or "")
        text, ok = QInputDialog.getText(
            self,
            "全局热键",
            "组合键（留空 = 禁用）：\n示例：Ctrl+Shift+Space",
            QLineEdit.EchoMode.Normal,
            current,
        )
        if not ok:
            return
        text = (text or "").strip()
        if text:
            try:
                win32_hotkey.parse_accel(text)
            except Exception:
                QMessageBox.warning(
                    self,
                    "热键无效",
                    f"无法解析热键「{text}」（示例：Ctrl+Shift+Space）。已保留原设置。",
                )
                return
        self._config.set("general", "hotkey", value=text)
        self._apply()
        self._hotkey_label.setText(text or "未设置")

        # 已注册过的热键需要立刻改用新组合
        shell = getattr(self.window(), "_window_shell", None)
        if shell is not None and getattr(shell, "hotkey_registered", False):
            shell.install_hotkey()

    # ==================================================================
    # AI / Skill 状态
    # ==================================================================

    def _refresh_ai_status(self) -> None:
        """即时校验所选助手是否可用（原型里是一行绿色/红色状态文案）。"""
        t = get_tokens()
        provider = self._config.get("ai_assistant", "provider") or ""
        from ...services.ai_assistant import _resolve_cmd, _workspace_dir, detect_provider

        self._ai_workspace.setText(str(_workspace_dir(self._config)))

        if not provider:
            provider = detect_provider(self._config) or ""
            prefix = "自动检测到"
        else:
            prefix = "已选"

        if not provider:
            self._set_ai_status(
                "✗ 未检测到 Claude Code 或 Codex，AI 助手将不可用。"
                "请先安装对应 CLI，或检查 PATH。",
                t.danger,
            )
            return

        cmd = self._config.get("ai_assistant", f"{provider}_cmd", default=provider)
        path = _resolve_cmd(str(cmd or provider))
        if path:
            self._set_ai_status(f"✓ {prefix} {provider.capitalize()}：{path}", t.success)
        else:
            self._set_ai_status(
                f"✗ {provider.capitalize()} 命令未找到（config: "
                f"ai_assistant.{provider}_cmd = {cmd!r}）",
                t.danger,
            )

    def _set_ai_status(self, text: str, color: str) -> None:
        self._ai_status.setStyleSheet(
            f"QLabel#setSectionHint {{ font-size: 11px; color: {color}; }}"
        )
        self._ai_status.setText(text)

    def _refresh_skill_status(self) -> None:
        from ...services.ai_assistant import skill_sync_status

        st = skill_sync_status()
        synced = st.get("synced", {})
        claude = "已同步" if synced.get("claude") else "未同步"
        codex = "已同步" if synced.get("codex") else "未同步"
        self._skill_path.setText(
            f"{st['path']}\n"
            f"{'已就绪' if st['exists'] else '缺失'} · "
            f"版本 {st['version'] or '未标注'}\n"
            f"Claude Code {claude} · Codex {codex}"
        )

    def _on_edit_skill(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from ...services.ai_assistant import bundled_skill_path, ensure_bundled_skill

        ensure_bundled_skill()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(bundled_skill_path())))
        self._refresh_skill_status()

    def _on_sync_skill(self) -> None:
        from ...services.ai_assistant import sync_skill_to_hosts

        result = sync_skill_to_hosts()
        self._refresh_skill_status()
        targets = result if isinstance(result, dict) else {}
        done = ", ".join(sorted(k for k, v in targets.items() if v)) or "无可用宿主"
        self._flash(f"已同步 Skill 到：{done}")

    def _flash(self, message: str) -> None:
        """借主窗口的浮层做反馈（与全局交互一致）。"""
        flash = getattr(self.window(), "_flash_status", None)
        if callable(flash):
            flash(message)

    # ==================================================================
    # 主题
    # ==================================================================

    def refresh_theme(self) -> None:
        super().refresh_theme()
        self.body.setStyleSheet(expand_qss(_CONTENT_QSS))


class _PartitionDialog(QDialog):
    """单个分区的管理面板：改名 / 归档阈值 / 自动锁定 / 密码 / 删除。"""

    def __init__(
        self,
        task_service: TaskService,
        config: AppConfig,
        partition: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = task_service
        self._config = config
        self._partition = dict(partition)
        self._pid = str(partition["id"])

        t = get_tokens()
        self.setWindowTitle(f"管理分区 · {partition['name']}")
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        def field(label: str, widget: QWidget) -> QWidget:
            holder = QWidget()
            lay = QHBoxLayout(holder)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            name = QLabel(label)
            name.setStyleSheet(f"font-size: 12.5px; color: {t.text_primary};")
            lay.addWidget(name)
            lay.addStretch(1)
            lay.addWidget(widget)
            return holder

        self._name_edit = QLineEdit(partition["name"])
        self._name_edit.setFixedWidth(190)
        root.addWidget(field("名称", self._name_edit))

        self._archive_sw = ToggleSwitch()
        self._archive_sw.setChecked(bool(int(partition.get("archive_enabled", 1) or 0)))
        root.addWidget(field("启用自动归档", self._archive_sw))

        days = int(partition.get("archive_days", 0) or 0)
        self._archive_edit = QLineEdit("" if days >= ARCHIVE_NEVER else str(days))
        self._archive_edit.setPlaceholderText("留空 = 永不归档")
        self._archive_edit.setFixedWidth(190)
        root.addWidget(field("归档阈值（天）", self._archive_edit))

        self._lock_edit = QLineEdit(str(partition.get("auto_lock_minutes", 3) or 0))
        self._lock_edit.setFixedWidth(190)
        root.addWidget(field("自动锁定（分）", self._lock_edit))

        has_pwd = bool(partition.get("password"))
        self._pwd_btn = QPushButton("🔒 修改密码" if has_pwd else "🔓 设置密码")
        self._pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pwd_btn.clicked.connect(self._on_password)
        root.addWidget(field("密码", self._pwd_btn))

        self._default_sw = ToggleSwitch()
        self._default_sw.setChecked(
            self._config.get("general", "default_partition", default="") == self._pid
        )
        root.addWidget(field("设为默认分区", self._default_sw))

        root.addStretch(1)

        buttons = QDialogButtonBox()
        buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        self._delete_btn = buttons.addButton(
            "删除分区", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self._on_button_clicked)
        root.addWidget(buttons)

        from ...utils.win32_theme import is_dark_mode_supported, set_window_dark_mode

        if is_dark_mode_supported():
            from ...utils.design_tokens import is_dark

            set_window_dark_mode(self, is_dark())

    def _on_button_clicked(self, button) -> None:
        if button is self._delete_btn:
            self._on_delete()

    def _on_password(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        has_pwd, stored = self._svc.check_partition_password(self._pid)
        if has_pwd:
            old, ok = QInputDialog.getText(
                self,
                "修改密码",
                "输入旧密码（留空 = 清除密码）：",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            if not old:
                self._svc.set_partition_password(self._pid, "")
                self._pwd_btn.setText("🔓 设置密码")
                return
            if old != stored:
                QMessageBox.warning(self, "密码错误", "旧密码不正确，已取消修改。")
                return
        new, ok = QInputDialog.getText(
            self,
            "设置密码",
            "输入新密码（留空 = 清除密码）：",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        self._svc.set_partition_password(self._pid, new)
        self._pwd_btn.setText("🔒 修改密码" if new else "🔓 设置密码")

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "名称不能为空", "请填写分区名称。")
            return

        raw_days = self._archive_edit.text().strip()
        try:
            days = ARCHIVE_NEVER if not raw_days else max(0, int(raw_days))
        except ValueError:
            QMessageBox.warning(
                self, "数值无效", "归档阈值请填整数天数，留空表示永不归档。"
            )
            return
        try:
            lock = max(0, int(self._lock_edit.text().strip() or 0))
        except ValueError:
            QMessageBox.warning(self, "数值无效", "自动锁定请填整数分钟数。")
            return

        if name != self._partition["name"]:
            if any(
                p["name"] == name and p["id"] != self._pid
                for p in self._svc.get_all_partitions()
            ):
                QMessageBox.warning(self, "名称重复", f"分区「{name}」已存在。")
                return
            self._svc.upsert_partition(name, partition_id=self._pid)
            _log.info("Partition renamed: id=%s new_name=%s", self._pid, name)

        self._svc.set_partition_archive_enabled(self._pid, self._archive_sw.isChecked())
        self._svc.set_partition_archive_days(self._pid, days)
        self._svc.set_partition_auto_lock(self._pid, lock)

        self._apply_default_partition()
        self.accept()

    def _apply_default_partition(self) -> None:
        """默认分区最多一个：勾选即抢占，取消则回落到另一个分区。"""
        current = self._config.get("general", "default_partition", default="")
        if self._default_sw.isChecked():
            self._config.set("general", "default_partition", value=self._pid)
            return
        if current != self._pid:
            return
        others = [p for p in self._svc.get_all_partitions() if p["id"] != self._pid]
        self._config.set(
            "general", "default_partition", value=others[0]["id"] if others else ""
        )

    def _on_delete(self) -> None:
        name = self._partition["name"]
        count = self._svc.count_tasks_in_partition(self._pid)
        if count > 0:
            QMessageBox.warning(
                self,
                "无法删除",
                f"分区「{name}」中还有 {count} 个任务，请先移动或删除这些任务。",
            )
            return
        if len(self._svc.get_all_partitions()) <= 1:
            QMessageBox.warning(self, "无法删除", "至少需要保留一个分区。")
            return
        answer = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除分区「{name}」吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if self._config.get("general", "default_partition", default="") == self._pid:
            others = [
                p for p in self._svc.get_all_partitions() if p["id"] != self._pid
            ]
            self._config.set(
                "general", "default_partition", value=others[0]["id"] if others else ""
            )
        self._svc.delete_partition(self._pid)
        _log.info("Partition deleted via settings drawer: id=%s", self._pid)
        self.accept()


__all__ = ["SETTINGS_WIDTH", "SettingsDrawer"]
