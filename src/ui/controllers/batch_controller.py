"""BatchController — batch operations and task management console page."""

from __future__ import annotations

import logging
from datetime import date as _date, datetime as _datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_filter import TaskFilter
from ...models.task_status import TaskStatus
from ...services.task_service import TaskService

from ...utils.signal_bus import get_signal_bus
from ...utils.widget_utils import combo_width

_log = logging.getLogger("runlog")


class BatchController(QObject):
    """Manages batch operations and the task management console page.

    Signals:
        data_changed(): trigger external data refresh
        status_message(msg): flash message on status bar
        view_switch_requested(view): request MainWindow to switch views
    """

    data_changed = Signal()
    status_message = Signal(str)

    def __init__(
        self,
        task_service: TaskService,
        config: AppConfig,
        repository: TaskRepository,
        partition_ctrl,  # PartitionController
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._svc = task_service
        self._config = config
        self._repo = repository
        self._part = partition_ctrl
        self._bus = get_signal_bus()

        # Page state
        self._built = False
        self._page = 0
        self._page_size = config.get("general", "page_size", default=20)
        self._total_count = 0
        self._pending_action: dict | None = None
        self._tag_sort: str | None = None  # tag whose tasks are brought to front

        # Widgets (populated by build_page)
        self._batch_task_model = None
        self._confirm_bar = None
        self._confirm_label = None
        self._confirm_ok_btn = None
        self._batch_search = None
        self._batch_status_combo = None
        self._batch_priority_combo = None
        self._batch_created_from = None
        self._batch_created_to = None
        self._batch_deadline_from = None
        self._batch_deadline_to = None
        self._batch_progress_combo = None
        self._batch_tag_input = None
        self._batch_archive_combo = None
        self._batch_page_label = None
        self._batch_prev_btn = None
        self._batch_next_btn = None
        self._batch_page_size_combo = None
        self._batch_toolbar2 = None
        self._batch_tag_panel = None

    # ------------------------------------------------------------------
    # Public API — called from MainWindow
    # ------------------------------------------------------------------

    def build_page(self) -> QWidget:
        """Lazily build and return the batch management console page."""
        if self._built:
            return self._page_widget
        self._built = True

        from ..task_list.batch_toolbar import BatchToolbar
        from ..task_list.task_list_model import COL_ARCHIVED, TaskListModel
        from ..task_list.task_list_view import TaskListView
        from ..widgets.calendar_popup import CalendarPopup
        from ..widgets.dropdown import DropdownWidget
        from ..widgets.tag_management_panel import TagManagementPanel

        batch_page = QWidget()
        batch_page_layout = QHBoxLayout(batch_page)
        batch_page_layout.setContentsMargins(0, 0, 0, 0)
        batch_page_layout.setSpacing(0)

        # -- Left sidebar (180px) --
        self._manage_sidebar = QWidget()
        self._manage_sidebar.setObjectName("manageSidebar")
        self._manage_sidebar.setFixedWidth(180)
        sidebar_layout = QVBoxLayout(self._manage_sidebar)
        sidebar_layout.setContentsMargins(8, 6, 8, 6)
        sidebar_layout.setSpacing(3)

        SIDEBAR_LABEL = "font-size: 10px; font-weight: bold; border: none; padding-top: 4px;"
        SIDEBAR_INPUT = "font-size: 10px; padding: 2px 4px;"
        SIDEBAR_BTN = "QPushButton { font-size: 10px; padding: 4px 8px; }"

        def _add_sep():
            s = QWidget()
            s.setObjectName("sidebarSep")
            s.setFixedHeight(1)
            sidebar_layout.addWidget(s)

        def _add_label(text: str):
            lb = QLabel(text)
            lb.setStyleSheet(SIDEBAR_LABEL)
            sidebar_layout.addWidget(lb)

        def _add_date_row(placeholder: str) -> QLineEdit:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            le.setStyleSheet(SIDEBAR_INPUT)
            le.setReadOnly(True)
            le.mousePressEvent = lambda e, le_=le: self._open_date_popup(le_)
            row_layout.addWidget(le, 1)
            clear_btn = QPushButton("×")
            clear_btn.setFixedSize(16, 16)
            clear_btn.setObjectName("sidebarClearBtn")
            clear_btn.setStyleSheet("QPushButton { font-size: 10px; padding: 0; border: none; }")
            clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            clear_btn.clicked.connect(lambda _, le_=le: (le_.clear(), self.refresh_page()))
            row_layout.addWidget(clear_btn)
            sidebar_layout.addWidget(row)
            return le

        # ---- 筛选 ----
        _add_label("🔍 筛选")
        _add_label("关键词")
        self._batch_search = QLineEdit()
        self._batch_search.setPlaceholderText("搜索...")
        self._batch_search.setStyleSheet(SIDEBAR_INPUT)
        self._batch_search_timer = QTimer(self)
        self._batch_search_timer.setSingleShot(True)
        self._batch_search_timer.timeout.connect(self._on_batch_search)
        self._batch_search.textChanged.connect(lambda: self._batch_search_timer.start(300))
        sidebar_layout.addWidget(self._batch_search)

        _add_label("状态")
        self._batch_status_combo = DropdownWidget()
        self._batch_status_combo.addItem("全部", None)
        for s in (TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE, TaskStatus.OVERDUE):
            self._batch_status_combo.addItem(s.display_name, s)
        self._batch_status_combo.currentIndexChanged.connect(self.refresh_page)
        sidebar_layout.addWidget(self._batch_status_combo)

        _add_label("优先级")
        self._batch_priority_combo = DropdownWidget()
        self._batch_priority_combo.addItem("全部", None)
        for val, label in [(0, "● 紧急"), (1, "● 重要"), (2, "● 关注"), (3, "● 普通")]:
            self._batch_priority_combo.addItem(label, val)
        self._batch_priority_combo.currentIndexChanged.connect(self.refresh_page)
        sidebar_layout.addWidget(self._batch_priority_combo)

        _add_label("创建时间")
        self._batch_created_from = _add_date_row("起始日期")
        self._batch_created_to = _add_date_row("结束日期")
        _add_label("截止时间")
        self._batch_deadline_from = _add_date_row("起始日期")
        self._batch_deadline_to = _add_date_row("结束日期")

        _add_label("进度")
        self._batch_progress_combo = DropdownWidget()
        self._batch_progress_combo.addItem("全部", (0, 100))
        for label, rng in [("0%", (0, 0)), ("1-25%", (1, 25)), ("26-50%", (26, 50)),
                            ("51-75%", (51, 75)), ("100%", (100, 100))]:
            self._batch_progress_combo.addItem(label, rng)
        self._batch_progress_combo.currentIndexChanged.connect(self.refresh_page)
        sidebar_layout.addWidget(self._batch_progress_combo)

        _add_label("标签")
        self._batch_tag_input = QLineEdit()
        self._batch_tag_input.setPlaceholderText("#标签1 #标签2")
        self._batch_tag_input.setStyleSheet(SIDEBAR_INPUT)
        self._batch_tag_timer = QTimer(self)
        self._batch_tag_timer.setSingleShot(True)
        self._batch_tag_timer.timeout.connect(self.refresh_page)
        self._batch_tag_input.textChanged.connect(lambda: self._batch_tag_timer.start(300))
        sidebar_layout.addWidget(self._batch_tag_input)

        _add_label("归档状态")
        self._batch_archive_combo = DropdownWidget()
        self._batch_archive_combo.addItem("全部", "all")
        self._batch_archive_combo.addItem("未归档", "unarchived")
        self._batch_archive_combo.addItem("已归档", "archived")
        self._batch_archive_combo.currentIndexChanged.connect(self.refresh_page)
        sidebar_layout.addWidget(self._batch_archive_combo)

        _add_sep()
        _add_label("🛠 操作")
        self._archive_btn = QPushButton("归档已完成")
        self._archive_btn.setStyleSheet(SIDEBAR_BTN)
        self._archive_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._archive_btn.clicked.connect(self.manual_archive)
        sidebar_layout.addWidget(self._archive_btn)
        self._clear_archived_btn = QPushButton("清除已归档")
        self._clear_archived_btn.setStyleSheet(SIDEBAR_BTN)
        self._clear_archived_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_archived_btn.clicked.connect(self.clear_archived)
        sidebar_layout.addWidget(self._clear_archived_btn)
        sidebar_layout.addStretch()


        # -- Main content area --
        batch_main = QWidget()
        batch_layout = QVBoxLayout(batch_main)
        batch_layout.setContentsMargins(8, 4, 8, 4)
        batch_layout.setSpacing(4)

        self._batch_toolbar2 = BatchToolbar()
        self._batch_toolbar2.select_all_requested.connect(self.select_all)
        self._batch_toolbar2.deselect_all_requested.connect(self.deselect_all)
        self._batch_toolbar2.export_requested.connect(self._on_batch_export)
        batch_layout.addWidget(self._batch_toolbar2)

        self._batch_task_model = TaskListModel()
        self._batch_task_view = TaskListView(self._repo, task_service=self._svc)
        self._batch_task_view.set_model(self._batch_task_model)
        self._batch_task_view.setSelectionBehavior(
            self._batch_task_view.SelectionBehavior.SelectRows
        )
        self._batch_task_view.task_selected.connect(self._on_batch_task_selected)
        self._batch_task_view.batch_status_change.connect(self.batch_status_change)
        self._batch_task_view.batch_urgency_change.connect(self.batch_urgency_change)
        self._batch_task_view.batch_delete.connect(self.batch_delete)
        self._batch_task_view.batch_suspend.connect(self.batch_suspend)
        self._batch_task_view.batch_restart.connect(self.batch_restart)
        self._batch_task_view.batch_postpone.connect(self.batch_postpone)
        self._batch_task_view.batch_move_partition.connect(self.batch_move_partition)
        self._batch_task_model.dataChanged.connect(self._on_batch_model_data_changed)
        batch_layout.addWidget(self._batch_task_view, 1)

        # Pagination
        batch_pager = QWidget()
        batch_pager_layout = QHBoxLayout(batch_pager)
        batch_pager_layout.setContentsMargins(4, 2, 4, 2)
        batch_pager_layout.setSpacing(4)
        batch_pager_layout.addStretch()
        self._batch_prev_btn = QPushButton("‹")
        self._batch_prev_btn.setObjectName("navBtn")
        self._batch_prev_btn.setFixedWidth(28)
        self._batch_prev_btn.clicked.connect(self._on_page_prev)
        batch_pager_layout.addWidget(self._batch_prev_btn)
        self._batch_page_label = QLabel("1 / 1")
        self._batch_page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        batch_pager_layout.addWidget(self._batch_page_label)
        self._batch_next_btn = QPushButton("›")
        self._batch_next_btn.setObjectName("navBtn")
        self._batch_next_btn.setFixedWidth(28)
        self._batch_next_btn.clicked.connect(self._on_page_next)
        batch_pager_layout.addWidget(self._batch_next_btn)
        self._batch_page_size_combo = DropdownWidget()
        self._batch_page_size_combo.setFixedWidth(combo_width(4))
        for n in ["20", "50", "100"]:
            self._batch_page_size_combo.addItem(n, int(n))
        self._batch_page_size_combo.setCurrentText(str(self._page_size))
        self._batch_page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        batch_pager_layout.addWidget(self._batch_page_size_combo)
        batch_layout.addWidget(batch_pager)

        # Confirm bar
        self._confirm_bar = QWidget()
        self._confirm_bar.setFixedHeight(48)
        self._confirm_bar.setVisible(False)
        confirm_layout = QHBoxLayout(self._confirm_bar)
        confirm_layout.setContentsMargins(12, 4, 12, 4)
        self._confirm_label = QLabel("")
        confirm_layout.addWidget(self._confirm_label, 1)
        self._confirm_ok_btn = QPushButton("确认")
        self._confirm_ok_btn.setFixedHeight(28)
        confirm_layout.addWidget(self._confirm_ok_btn)
        confirm_cancel_btn = QPushButton("取消")
        confirm_cancel_btn.setFixedHeight(28)
        confirm_cancel_btn.clicked.connect(self._hide_confirm)
        confirm_layout.addWidget(confirm_cancel_btn)
        batch_layout.addWidget(self._confirm_bar)

        # Splitter: content (70%) + tag panel (30%)
        self._batch_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._batch_splitter.setHandleWidth(2)
        self._batch_splitter.setChildrenCollapsible(False)
        batch_left = QWidget()
        batch_left_layout = QHBoxLayout(batch_left)
        batch_left_layout.setContentsMargins(0, 0, 0, 0)
        batch_left_layout.setSpacing(0)
        batch_left_layout.addWidget(self._manage_sidebar)
        batch_left_layout.addWidget(batch_main, 1)
        self._batch_splitter.addWidget(batch_left)
        self._batch_tag_panel = TagManagementPanel(
            self._repo, config=self._config, task_service=self._svc,
        )
        self._batch_splitter.addWidget(self._batch_tag_panel)
        # Sync the tag panel to the currently active partition
        pid = self._part.active_id or None
        self._batch_tag_panel.set_partition_id(pid)
        self._batch_splitter.setStretchFactor(0, 1)
        self._batch_splitter.setStretchFactor(1, 0)

        batch_page_layout.addWidget(self._batch_splitter)

        # Tag panel signal connections
        self._batch_tag_panel.tag_changed.connect(lambda: self._bus.tag_changed.emit())
        self._bus.task_created.connect(lambda *_: self._batch_tag_panel.refresh())
        self._bus.task_updated.connect(lambda *_: self._batch_tag_panel.refresh())
        self._bus.task_deleted.connect(lambda *_: self._batch_tag_panel.refresh())
        self._bus.tag_changed.connect(lambda *_: self.refresh_page())

        # Bidirectional task list <-> tag panel interaction
        self._batch_task_view.selection_cleared.connect(self._on_batch_selection_cleared)
        self._batch_tag_panel.tag_clicked.connect(self._on_tag_panel_clicked)

        self._page_widget = batch_page
        return batch_page

    def refresh_page(self) -> None:
        """Refresh batch page applying all sidebar filters."""
        if not self._built:
            return

        f = TaskFilter(show_archived=True, show_suspended=True)
        f.sort_by = []  # default: no sort

        if self._batch_search and self._batch_search.text().strip():
            f.search_text = self._batch_search.text().strip()

        status_val = self._batch_status_combo.currentData() if self._batch_status_combo else None
        if status_val:
            f.statuses = {status_val}

        pri_val = self._batch_priority_combo.currentData() if self._batch_priority_combo else None
        if pri_val is not None:
            f.urgencies = {pri_val}

        def _read_date_edit(attr_name: str) -> _date | None:
            obj = getattr(self, attr_name, None)
            if obj is None:
                return None
            text = obj.text().strip() if hasattr(obj, 'text') else ""
            if not text:
                return None
            try:
                return _date.fromisoformat(text)
            except (ValueError, TypeError):
                return None

        f.created_from = _read_date_edit("_batch_created_from")
        f.created_to = _read_date_edit("_batch_created_to")
        f.date_from = _read_date_edit("_batch_deadline_from")
        f.date_to = _read_date_edit("_batch_deadline_to")

        if self._batch_progress_combo:
            prog = self._batch_progress_combo.currentData()
            if prog:
                f.progress_min, f.progress_max = prog

        if self._batch_tag_input and self._batch_tag_input.text().strip():
            tags_text = self._batch_tag_input.text().strip()
            tags = {t.lstrip("#") for t in tags_text.split() if t}
            if tags:
                f.tags = tags

        archive_val = self._batch_archive_combo.currentData() if self._batch_archive_combo else "all"
        if archive_val == "unarchived":
            f.show_archived = False
        elif archive_val == "archived":
            f.show_archived = True

        pid = self._part.active_id or ""
        f.partition_id = pid
        f.limit = self._page_size
        f.offset = self._page * self._page_size

        tasks, self._total_count = self._svc.search_with_total(f)
        # Apply tag-based priority sort if a tag was clicked
        tasks = self._apply_tag_priority(tasks)
        self._batch_task_model.load_tasks(tasks)
        self._update_pagination()

    def set_active_partition(self, pid: str) -> None:
        """Set partition context for filtering and propagate to the tag panel."""
        if self._built and self._batch_tag_panel is not None:
            self._batch_tag_panel.set_partition_id(pid)

    def batch_status_change(self, ids: list[str], status) -> None:
        """Handle batch status change (edit view → confirm dialog; batch view → confirm bar)."""
        if not ids:
            return
        reply = QMessageBox.question(
            self._batch_task_view, "批量操作",
            f"确认更改 {len(ids)} 个任务的状态？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self._svc.batch_update_status(ids, status)
            self._batch_task_model.set_checked_ids(set())
            self.data_changed.emit()
            self._batch_toolbar2.reset_toggle()
            self.status_message.emit(f"已更改 {len(ids)} 个任务状态")
        # Note: batch-view confirm bar path is simplified for now

    def batch_urgency_change(self, ids: list[str], urgency: int) -> None:
        if not ids:
            return
        self._svc.batch_update_urgency(ids, urgency)
        updated = self._svc.get_task(ids[0])
        if updated and hasattr(self, '_batch_toolbar2'):
            self._batch_toolbar2.reset_toggle()
        self.data_changed.emit()
        self.status_message.emit(f"已更改 {len(ids)} 个任务的优先级")

    def batch_delete(self, ids: list[str]) -> None:
        if not ids:
            return
        reply = QMessageBox.question(
            self._batch_task_view, "批量删除",
            f"确认删除 {len(ids)} 个任务？此操作不可恢复。",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self._svc.batch_delete(ids)
            self.data_changed.emit()
            self.status_message.emit(f"已删除 {len(ids)} 个任务")

    def batch_suspend(self, ids: list[str]) -> None:
        if not ids:
            return
        self._svc.batch_suspend(ids)
        self.data_changed.emit()
        self.status_message.emit(f"已中止 {len(ids)} 个任务")

    def batch_restart(self, ids: list[str]) -> None:
        if not ids:
            return
        self._svc.batch_restart(ids)
        self.data_changed.emit()
        self.status_message.emit(f"已重启 {len(ids)} 个任务")

    def batch_postpone(self, ids: list[str], days: int) -> None:
        if not ids:
            return
        self._svc.batch_postpone(ids, days)
        self.data_changed.emit()
        self.status_message.emit(f"已延后 {len(ids)} 个任务 +{days}天")

    def batch_move_partition(self, ids: list[str]) -> None:
        """Move selected tasks to another partition with password verification."""
        if not ids:
            return
        from_partition_id = self._part.active_id or ""
        from_pw = self._part.passwords.get(from_partition_id, "")
        if from_pw:
            pw, ok = QInputDialog.getText(
                self._batch_task_view, "密码验证",
                f"当前分区设有密码，请输入密码：",
                QLineEdit.EchoMode.Password,
            )
            if not ok or pw.strip() != from_pw:
                if ok:
                    QMessageBox.warning(self._batch_task_view, "密码错误", "密码不正确")
                return

        parts = self._svc.get_all_partitions()
        name_map = {p["id"]: p["name"] for p in parts}
        from_name = name_map.get(from_partition_id, "当前分区")

        dlg = QMessageBox(self._batch_task_view)
        dlg.setWindowTitle("选择目标分区")
        dlg.setText(f"从 [{from_name}] 迁移 {len(ids)} 个任务到：")
        lst = QListWidget()
        for p in parts:
            if p["id"] == from_partition_id:
                continue
            has_pw = bool(self._part.passwords.get(p["id"], ""))
            item = QListWidgetItem(f"{'🔒 ' if has_pw else ''}{p['name']}")
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            lst.addItem(item)
        if lst.count() == 0:
            QMessageBox.information(dlg, "无目标分区", "没有其他分区可迁移。")
            return
        dlg.layout().addWidget(lst, 1, 0, 1, dlg.layout().columnCount())
        dlg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        dlg.setMinimumWidth(320)
        if dlg.exec() != QMessageBox.StandardButton.Ok or not lst.currentItem():
            return

        to_partition_id = lst.currentItem().data(Qt.ItemDataRole.UserRole)
        to_pw = self._part.passwords.get(to_partition_id, "")
        if to_pw:
            pw2, ok2 = QInputDialog.getText(
                self._batch_task_view, "目标分区密码",
                f"目标分区设有密码，请输入密码：",
                QLineEdit.EchoMode.Password,
            )
            if not ok2 or pw2.strip() != to_pw:
                if ok2:
                    QMessageBox.warning(self._batch_task_view, "密码错误", "目标分区密码不正确")
                return

        reply = QMessageBox.question(
            self._batch_task_view, "确认迁移",
            f"确认将 {len(ids)} 个任务从 [{from_name}] 迁移到 [{name_map.get(to_partition_id, '目标')}]？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            moved = self._svc.batch_move_partition(ids, to_partition_id)
            self.data_changed.emit()
            self.status_message.emit(f"已迁移 {moved} 个任务")

    def manual_archive(self) -> None:
        """Archive all completed tasks in the current partition."""
        pid = self._part.active_id or ""
        if not pid:
            return
        f = TaskFilter(partition_id=pid, statuses={TaskStatus.DONE}, show_archived=False)
        done_tasks = self._svc.search(f)
        if not done_tasks:
            QMessageBox.information(self._batch_task_view, "无需归档", "当前分区没有可归档的已完成任务。")
            return
        ids = [t.id for t in done_tasks]
        q = QMessageBox.question(
            self._batch_task_view, "确认归档",
            f"确认归档 {len(ids)} 个已完成的任务吗？",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if q == QMessageBox.StandardButton.Ok:
            self._svc.archive_batch(ids)
            self.refresh_page()
            self.data_changed.emit()
            self.status_message.emit(f"已归档 {len(ids)} 个任务")

    def clear_archived(self) -> None:
        """Permanently delete all archived tasks in the current partition."""
        pid = self._part.active_id or ""
        if not pid:
            return
        f = TaskFilter(partition_id=pid, show_archived=True)
        all_tasks = self._svc.search(f)
        archived_ids = [t.id for t in all_tasks if t.archived]
        if not archived_ids:
            QMessageBox.information(self._batch_task_view, "无需清理", "当前分区没有已归档的任务。")
            return
        q = QMessageBox.question(
            self._batch_task_view, "⚠ 确认清除",
            f"确定要永久删除 {len(archived_ids)} 个已归档任务吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if q == QMessageBox.StandardButton.Yes:
            self._svc.batch_delete(archived_ids)
            self.refresh_page()
            self.data_changed.emit()
            self.status_message.emit(f"已清除 {len(archived_ids)} 个已归档任务")

    def select_all(self) -> None:
        if self._batch_task_model:
            all_ids = {t.id for t in self._batch_task_model.tasks}
            self._batch_task_model.set_checked_ids(all_ids)

    def deselect_all(self) -> None:
        if self._batch_task_model:
            self._batch_task_model.set_checked_ids(set())

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_batch_search(self) -> None:
        self._page = 0
        self.refresh_page()

    def _on_page_prev(self) -> None:
        if self._page > 0:
            self._page -= 1
            self.refresh_page()

    def _on_page_next(self) -> None:
        if (self._page + 1) * self._page_size < self._total_count:
            self._page += 1
            self.refresh_page()

    def _on_page_size_changed(self, _index: int) -> None:
        if self._batch_page_size_combo:
            self._page_size = self._batch_page_size_combo.currentData()
            self._page = 0
            self.refresh_page()

    def _on_batch_task_selected(self, task: Task) -> None:
        if self._batch_task_model:
            self._batch_task_model.set_highlighted_task(task.id)
        # Notify tag panel to bold the selected task's tags
        if self._batch_tag_panel:
            self._batch_tag_panel.clear_selection()
            self._batch_tag_panel.highlight_tags(set(task.tags))

    def _on_batch_selection_cleared(self) -> None:
        """Clear tag emphasis when task selection is cleared."""
        if self._batch_tag_panel:
            self._batch_tag_panel.clear_selection()
            self._batch_tag_panel.highlight_tags(set())

    def _on_tag_panel_clicked(self, tag: str) -> None:
        """Reorder task list so tasks carrying `tag` appear first.
        Clicking the same tag again toggles off the reorder.
        Tag panel selection is preserved for rename/merge operations."""
        self._tag_sort = None if self._tag_sort == tag else tag
        self.refresh_page()

    def _apply_tag_priority(self, tasks: list[Task]) -> list[Task]:
        """Stable reorder: tasks carrying the active tag move to the front.
        All tasks remain visible — this is a reorder, not a filter."""
        tag = self._tag_sort
        if not tag:
            return tasks
        return sorted(
            tasks,
            key=lambda t: 0 if tag.lower() in {x.lower() for x in (t.tags or [])} else 1,
        )

    def _on_batch_model_data_changed(self) -> None:
        if self._batch_toolbar2:
            ids = self._batch_task_model.checked_task_ids()
            self._batch_toolbar2.set_selected(ids)

    def _on_batch_export(self, fmt: str) -> None:
        pid = self._part.active_id or ""
        f = TaskFilter(partition_id=pid, show_archived=True)
        tasks = self._svc.search(f)
        name_map = self._svc.get_partition_name_map()
        pname = name_map.get(pid, "默认分区")

        if fmt == "md":
            from ...services.md_exporter import MarkdownExporter
            path, _ = QFileDialog.getSaveFileName(
                self._page_widget, "导出 Markdown", f"{pname}.md",
                "Markdown (*.md)",
            )
            if path:
                MarkdownExporter().export_file(tasks, path)
                self.status_message.emit(f"已导出: {path}")
        elif fmt == "xlsx":
            try:
                from ...services.task_exporter import export_xlsx
                path, _ = QFileDialog.getSaveFileName(
                    self._page_widget, "导出 Excel", f"{pname}.xlsx",
                    "Excel (*.xlsx)",
                )
                if path:
                    export_xlsx(tasks, path)
                    self.status_message.emit(f"已导出: {path}")
            except ImportError:
                QMessageBox.warning(self._page_widget, "错误", "需要安装 openpyxl 库")
        else:
            self.status_message.emit("不支持的导出格式")

    def _update_pagination(self) -> None:
        if not self._built:
            return
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        self._batch_page_label.setText(f"{self._page + 1} / {total_pages}")
        self._batch_prev_btn.setEnabled(self._page > 0)
        self._batch_next_btn.setEnabled((self._page + 1) * self._page_size < self._total_count)

    def _open_date_popup(self, line_edit: QLineEdit) -> None:
        from ..widgets.calendar_popup import CalendarPopup
        popup = CalendarPopup(line_edit)
        popup.date_selected.connect(lambda d: (
            line_edit.setText(d.toString("yyyy-MM-dd")),
            self.refresh_page(),
        ))
        popup.popup()

    def _hide_confirm(self) -> None:
        if self._confirm_bar:
            self._confirm_bar.setVisible(False)
        self._pending_action = None

    def _emit_view_switch(self, view: str) -> None:
        """Request MainWindow to switch views (via signal or direct call)."""
        # Emitted indirectly — MainWindow connects batch_ctrl to its _switch_view
        pass

    # ------------------------------------------------------------------
    # Public properties for MainWindow access
    # ------------------------------------------------------------------

    @property
    def splitter(self):
        return self._batch_splitter if self._built else None

    @property
    def tag_panel(self):
        return self._batch_tag_panel

    @property
    def page_widget(self):
        return self._page_widget if self._built else None
