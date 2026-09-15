"""TaskDrawer —— 右侧滑入式任务维护抽屉（阶段 4）。

替代「常驻编辑器」的交互：单击时间轴/图谱只选中，**双击**打开抽屉，
保存后自动收起，<kbd>Esc</kbd> 关闭。

组件职责：
* 头部：状态徽章 + 标题 + 关闭按钮
* 字段：Markdown 原文 / 标签 / 状态 / 进度 / 优先级
* 活动撰写器：调用 ``TaskService.append_activity``（只发一次信号）
* 活动时间线：最近若干条记录
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...models.task_status import TaskStatus
from ...services.task_service import TaskService
from ...utils.design_tokens import get_tokens, is_dark, surface_color

#: 抽屉宽度
DRAWER_WIDTH = 380
#: 滑入/滑出时长（毫秒）
ANIM_MS = 180

_STATUS_ORDER = (TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE, TaskStatus.OVERDUE)
_URGENCY_LABELS = ((0, "紧急"), (1, "重要"), (2, "关注"), (3, "普通"))


class TaskDrawer(QWidget):
    """右侧维护抽屉。

    Signals:
        saved(task_id): 保存成功
        closed(): 抽屉收起
    """

    saved = Signal(str)
    closed = Signal()

    def __init__(
        self,
        task_service: TaskService,
        parent: QWidget | None = None,
        *,
        animate: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("taskDrawer")
        self._svc = task_service
        self._task = None
        self._animate = animate
        self._anim: QPropertyAnimation | None = None
        self._showing = False

        self.setFixedWidth(DRAWER_WIDTH)
        self.hide()

        self._build_ui()
        if animate:
            self._anim = QPropertyAnimation(self, b"pos", self)
            self._anim.setDuration(ANIM_MS)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.finished.connect(self._on_anim_finished)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = get_tokens()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        self._status_badge = QLabel("—")
        self._status_badge.setStyleSheet("font-size: 11px; font-weight: bold;")
        head.addWidget(self._status_badge)
        # 原型 .dr-h .t{font:700 15px}——与设置抽屉同层级，此前是 14px。
        self._title_label = QLabel("")
        self._title_label.setObjectName("drawerTitle")
        self._title_label.setWordWrap(True)
        head.addWidget(self._title_label, 1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("drawerClose")
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip("关闭 (Esc)")
        close_btn.clicked.connect(self.close_drawer)
        head.addWidget(close_btn)
        root.addLayout(head)

        root.addWidget(QLabel("Markdown："))
        self._md_edit = QTextEdit()
        self._md_edit.setObjectName("drawerMd")
        self._md_edit.setMinimumHeight(60)
        root.addWidget(self._md_edit)

        tags_row = QHBoxLayout()
        tags_row.addWidget(QLabel("标签："))
        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("#标签1 #标签2")
        tags_row.addWidget(self._tags_edit, 1)
        root.addLayout(tags_row)

        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("状态："))
        self._status_combo = QComboBox()
        for status in _STATUS_ORDER:
            self._status_combo.addItem(status.display_name, status)
        meta_row.addWidget(self._status_combo)
        meta_row.addWidget(QLabel("优先级："))
        self._urgency_combo = QComboBox()
        for level, name in _URGENCY_LABELS:
            self._urgency_combo.addItem(name, level)
        meta_row.addWidget(self._urgency_combo)
        meta_row.addStretch()
        root.addLayout(meta_row)

        prog_row = QHBoxLayout()
        prog_row.addWidget(QLabel("进度："))
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setFixedHeight(16)
        prog_row.addWidget(self._progress, 1)
        root.addLayout(prog_row)

        root.addWidget(QLabel("撰写进展："))
        self._log_edit = QTextEdit()
        self._log_edit.setObjectName("drawerLog")
        self._log_edit.setFixedHeight(52)
        self._log_edit.setPlaceholderText("输入进展内容…")
        root.addWidget(self._log_edit)
        log_row = QHBoxLayout()
        log_row.addStretch()
        self._log_btn = QPushButton("追加进展")
        self._log_btn.clicked.connect(self._on_append_activity)
        log_row.addWidget(self._log_btn)
        root.addLayout(log_row)

        root.addWidget(QLabel("活动时间线："))
        self._log_list = QListWidget()
        self._log_list.setObjectName("drawerActivity")
        root.addWidget(self._log_list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.close_drawer)
        btn_row.addWidget(cancel)
        self._save_btn = QPushButton("保存")
        self._save_btn.setObjectName("saveBtn")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        root.addLayout(btn_row)

        # 与 side_drawer 一致走 --surface（#fbfaf6）。原先这里是 bg_secondary
        # （#ecebe5）——原型里那是**分段控件轨道的凹槽色**，整块刷上去会让
        # 抽屉比页面（--bg #f4f3ef）还暗，是「发灰」的直接来源之一。
        self.setStyleSheet(
            f"QWidget#taskDrawer {{ background: {surface_color(is_dark())};"
            f" border-left: 1px solid {t.border_primary}; }}"
        )

        # Esc 关闭（仅在抽屉拥有焦点时生效，避免抢占全局 Esc）
        from PySide6.QtGui import QKeySequence, QShortcut

        shortcut = QShortcut(QKeySequence("Esc"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.close_drawer)

    # ------------------------------------------------------------------
    # 打开 / 关闭
    # ------------------------------------------------------------------

    @property
    def current_task(self):
        return self._task

    @property
    def is_open(self) -> bool:
        return self._showing

    def open_task(self, task_id: str) -> bool:
        """载入任务并滑入；任务不存在返回 False。"""
        task = self._svc.get_task(task_id)
        if task is None:
            return False
        self._task = task
        self._populate(task)
        self._slide(in_=True)
        return True

    def close_drawer(self) -> None:
        self._slide(in_=False)

    def _slide(self, *, in_: bool) -> None:
        parent = self.parentWidget()
        if parent is None:
            self.setVisible(in_)
            self._showing = in_
            if not in_:
                self.closed.emit()
            return

        end_x = parent.width() - DRAWER_WIDTH if in_ else parent.width()
        top = 0
        height = parent.height()
        if in_:
            self.setGeometry(parent.width(), top, DRAWER_WIDTH, height)
            self.show()
            self.raise_()
            self._showing = True

        if self._anim is None:
            self.setGeometry(end_x, top, DRAWER_WIDTH, height)
            if not in_:
                self.hide()
                self._showing = False
                self.closed.emit()
            return

        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(QPoint(end_x, top))
        self._anim.start()

    def _on_anim_finished(self) -> None:
        if not self._showing:
            self.hide()
            self.closed.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """父窗口尺寸变化时贴住右侧（同值不重设，避免递归）。"""
        super().resizeEvent(event)
        parent = self.parentWidget()
        if parent is None:
            return
        x = parent.width() - DRAWER_WIDTH if self._showing else parent.width()
        if self.x() != x or self.height() != parent.height():
            self.setGeometry(x, 0, DRAWER_WIDTH, parent.height())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_drawer()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------

    def _populate(self, task) -> None:
        self._status_badge.setText(task.status.display_name)
        self._status_badge.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {task.status.display_color};"
        )
        self._title_label.setText(task.title)
        self._md_edit.setPlainText(task.raw_md)
        self._tags_edit.setText(" ".join(f"#{t}" for t in (task.tags or [])))

        index = self._status_combo.findData(task.status)
        self._status_combo.setCurrentIndex(index if index >= 0 else 0)
        urgency_index = self._urgency_combo.findData(getattr(task, "urgency", 3))
        self._urgency_combo.setCurrentIndex(urgency_index if urgency_index >= 0 else 3)
        self._progress.setValue(int(task.progress or 0))

        self._log_list.clear()
        for entry in reversed(task.activity_log[-12:]):
            ts = str(entry.get("ts", ""))[:16].replace("T", " ")
            self._log_list.addItem(f"{ts}  {entry.get('content', '')}")

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def _collect_tags(self) -> list[str]:
        import re

        return re.findall(r"#([\w一-鿿/\-]+)", self._tags_edit.text())

    def _on_append_activity(self) -> None:
        if self._task is None:
            return
        content = self._log_edit.toPlainText().strip()
        if not content:
            QMessageBox.information(self, "内容为空", "请输入进展内容后再提交。")
            return
        progress = self._progress.value()
        urgency = self._urgency_combo.currentData()
        updated = self._svc.append_activity(
            self._task.id, content, progress=progress, urgency=urgency,
        )
        if updated is None:
            return
        self._task = updated
        self._log_edit.clear()
        self._populate(updated)

    def _on_save(self) -> None:
        if self._task is None:
            return
        text = self._md_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "输入错误", "Markdown 内容不能为空。")
            return
        try:
            parsed = self._svc.parse_markdown(text)
        except ValueError:
            QMessageBox.warning(self, "解析失败", "Markdown 格式不正确，请检查。")
            return

        task = self._task
        previous_status = task.status
        task.title = parsed.clean_title
        task.tags = self._collect_tags() or parsed.tags
        task.scheduled_date = parsed.scheduled_date
        task.deadline_date = parsed.deadline_date
        task.deadline_time = parsed.deadline_time
        task.urgency = self._urgency_combo.currentData()
        combo_status = self._status_combo.currentData()
        if combo_status is not None and previous_status != TaskStatus.OVERDUE:
            task.status = combo_status
        if task.status == TaskStatus.DONE:
            task.progress = 100
            task.completed_at = task.deadline_date or datetime.now()
        else:
            task.progress = self._progress.value()
        task.updated_at = datetime.now()

        self._svc.save_task(task, previous_status=previous_status)
        self.saved.emit(task.id)
        self.close_drawer()

__all__ = ["ANIM_MS", "DRAWER_WIDTH", "TaskDrawer"]
