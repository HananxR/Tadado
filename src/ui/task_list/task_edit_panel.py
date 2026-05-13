"""Inline task editor panel with card-style timeline, detail editing, and multi-select."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ...utils.signal_bus import get_signal_bus

# ---------------------------------------------------------------------------
# Per-entry card widget in the timeline
# ---------------------------------------------------------------------------


class _TimelineEntryWidget(QWidget):
    """One card in the timeline: checkbox + timestamp + content (vertical layout)."""

    clicked = Signal(dict)
    checked_changed = Signal()

    def __init__(self, entry: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry
        self._selected = False

        self.setObjectName("entryCard")
        self.setMinimumHeight(44)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)

        # Checkbox
        self._check = QCheckBox()
        self._check.setFixedSize(18, 18)
        self._check.stateChanged.connect(lambda _: self.checked_changed.emit())
        row.addWidget(self._check, alignment=Qt.AlignmentFlag.AlignTop)

        # Right side: timestamp line + content line
        right = QVBoxLayout()
        right.setSpacing(2)

        icon = entry.get("icon", "●")
        color = entry.get("color", "#aaa")
        ts = _fmt_ts(entry.get("ts", ""), short=True)
        ts_label = QLabel(
            f'<span style="color:{color};font-weight:bold;">{icon}</span>'
            f' <span style="color:{color};font-size:10px;">{ts}</span>'
        )
        ts_label.setTextFormat(Qt.TextFormat.RichText)
        right.addWidget(ts_label)

        content = entry.get("content", "")
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setStyleSheet(
            "color: #444; font-size: 11px; border: none; background: transparent;"
        )
        right.addWidget(content_label)

        row.addLayout(right, 1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._entry)

    @property
    def entry(self) -> dict:
        return self._entry

    @property
    def is_checked(self) -> bool:
        return self._check.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._check.setChecked(checked)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


# ---------------------------------------------------------------------------
# Main edit panel
# ---------------------------------------------------------------------------


class TaskEditPanel(QWidget):
    """Right-side panel: raw_md editor, preview, save/delete, and card-style activity timeline."""

    def __init__(self, repository: TaskRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()
        self._signal_bus = get_signal_bus()
        self._current_task: Task | None = None
        self._original_md: str = ""
        self._entry_widgets: list[_TimelineEntryWidget] = []
        self._selected_entry: dict | None = None

        self.setObjectName("taskEditPanel")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(5)

        # --- Header ---
        header = QLabel("编辑任务")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header)

        # --- Markdown editor ---
        layout.addWidget(QLabel("Markdown："))
        self._md_edit = QTextEdit()
        self._md_edit.setObjectName("mdEditor")
        self._md_edit.setPlaceholderText("- [ ] TODO [#A] <2026-05-20> 标题 #标签")
        self._md_edit.setMaximumHeight(85)
        self._md_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._md_edit)

        # --- Live preview ---
        layout.addWidget(QLabel("预览："))
        self._preview = QLabel("(选择任务进行编辑)")
        self._preview.setTextFormat(Qt.TextFormat.RichText)
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet(
            "QLabel { color: #555; background: #f8f8f8; padding: 6px 8px;"
            " border-radius: 4px; font-size: 12px; }"
        )
        self._preview.setMinimumHeight(40)
        self._preview.setMaximumHeight(90)
        layout.addWidget(self._preview)

        # --- Action buttons ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._save_btn = QPushButton("保存")
        self._save_btn.setObjectName("saveBtn")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setObjectName("deleteBtn")
        self._delete_btn.clicked.connect(self._on_delete)
        self._delete_btn.setEnabled(False)
        self._copy_btn = QPushButton("复制MD")
        self._copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addWidget(self._copy_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ==================================================================
        # Timeline card
        # ==================================================================

        self._timeline_card = QWidget()
        self._timeline_card.setObjectName("timelineCard")
        tc = QVBoxLayout(self._timeline_card)
        tc.setContentsMargins(8, 6, 8, 6)
        tc.setSpacing(4)

        # -- Header + toolbar in one row --
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(8)
        tl_header = QLabel("活动时间线")
        tl_header.setStyleSheet("font-weight: bold; font-size: 12px; color: #444;")
        hdr_row.addWidget(tl_header)
        hdr_row.addStretch()

        self._select_all_cb = QCheckBox("全选")
        self._select_all_cb.setStyleSheet("font-size: 10px; color: #888; spacing: 3px;")
        self._select_all_cb.stateChanged.connect(self._on_select_all_changed)
        self._select_all_cb.setEnabled(False)
        hdr_row.addWidget(self._select_all_cb)

        self._delete_sel_btn = QPushButton("删选中")
        self._delete_sel_btn.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        self._delete_sel_btn.clicked.connect(self._on_delete_selected)
        self._delete_sel_btn.setEnabled(False)
        hdr_row.addWidget(self._delete_sel_btn)

        self._copy_tl_btn = QPushButton("复制MD")
        self._copy_tl_btn.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        self._copy_tl_btn.clicked.connect(self._on_copy_timeline_md)
        self._copy_tl_btn.setEnabled(False)
        hdr_row.addWidget(self._copy_tl_btn)
        tc.addLayout(hdr_row)

        tc.addWidget(_h_sep())

        # -- Scrollable entry cards --
        self._entry_scroll = QScrollArea()
        self._entry_scroll.setWidgetResizable(True)
        self._entry_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._entry_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._entry_container = QWidget()
        self._entry_container.setStyleSheet("background: transparent;")
        self._entry_layout = QVBoxLayout(self._entry_container)
        self._entry_layout.setContentsMargins(0, 0, 0, 0)
        self._entry_layout.setSpacing(4)
        self._entry_layout.addStretch()
        self._entry_scroll.setWidget(self._entry_container)

        self._entry_placeholder = QLabel("  (选择任务查看活动时间线)")
        self._entry_placeholder.setStyleSheet("color: #aaa; font-size: 11px; padding: 8px;")
        self._entry_placeholder.setVisible(False)
        tc.addWidget(self._entry_placeholder)
        tc.addWidget(self._entry_scroll, 1)
        self._entry_scroll.setVisible(False)

        tc.addWidget(_h_sep())

        # -- Status quick-toggle --
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.addWidget(QLabel("状态切换："))
        self._status_combo = QComboBox()
        for s in TaskStatus:
            self._status_combo.addItem(s.display_name, s)
        self._status_combo.setEnabled(False)
        self._status_combo.setFixedWidth(90)
        status_row.addWidget(self._status_combo)
        self._status_btn = QPushButton("切换")
        self._status_btn.clicked.connect(self._on_quick_status_change)
        self._status_btn.setEnabled(False)
        status_row.addWidget(self._status_btn)
        status_row.addStretch()
        tc.addLayout(status_row)

        # -- Unified log editor (progress input / detail editor merged) --
        log_label_row = QHBoxLayout()
        self._log_editor_label = QLabel("追加进展")
        self._log_editor_label.setStyleSheet("font-size: 11px; color: #888; font-weight: bold;")
        log_label_row.addWidget(self._log_editor_label)
        log_label_row.addStretch()
        tc.addLayout(log_label_row)

        self._log_edit = QTextEdit()
        self._log_edit.setPlaceholderText("输入进展内容…")
        self._log_edit.setMinimumHeight(46)
        self._log_edit.setMaximumHeight(72)
        self._log_edit.setEnabled(False)
        tc.addWidget(self._log_edit)

        # Buttons for the log editor (context-dependent)
        log_btn_row = QHBoxLayout()
        log_btn_row.setSpacing(6)

        self._log_save_btn = QPushButton("追加进展")
        self._log_save_btn.setObjectName("saveBtn")
        self._log_save_btn.clicked.connect(self._on_log_save)
        self._log_save_btn.setEnabled(False)

        self._log_delete_btn = QPushButton("删除此条")
        self._log_delete_btn.setStyleSheet("QPushButton { color: #c0392b; }")
        self._log_delete_btn.clicked.connect(self._on_log_delete)
        self._log_delete_btn.setEnabled(False)
        self._log_delete_btn.setVisible(False)

        self._log_cancel_btn = QPushButton("取消")
        self._log_cancel_btn.clicked.connect(self._on_log_cancel)
        self._log_cancel_btn.setEnabled(False)
        self._log_cancel_btn.setVisible(False)

        log_btn_row.addWidget(self._log_save_btn)
        log_btn_row.addWidget(self._log_delete_btn)
        log_btn_row.addWidget(self._log_cancel_btn)
        log_btn_row.addStretch()
        tc.addLayout(log_btn_row)

        layout.addWidget(self._timeline_card, 1)
        self._timeline_card.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_task(self, task: Task) -> None:
        self._current_task = task
        self._original_md = task.raw_md
        self._md_edit.blockSignals(True)
        self._md_edit.setText(task.raw_md)
        self._md_edit.blockSignals(False)

        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(True)
        self._status_combo.setEnabled(True)
        self._status_btn.setEnabled(True)
        self._log_edit.setEnabled(True)
        self._log_save_btn.setEnabled(True)
        self._timeline_card.setVisible(True)
        self._select_all_cb.setEnabled(True)
        self._copy_tl_btn.setEnabled(True)

        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == task.status:
                self._status_combo.setCurrentIndex(i)
                break

        self._update_preview()
        self._refresh_timeline()
        self._reset_log_editor()

    def clear(self) -> None:
        self._current_task = None
        self._original_md = ""
        self._md_edit.blockSignals(True)
        self._md_edit.clear()
        self._md_edit.blockSignals(False)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._status_combo.setEnabled(False)
        self._status_btn.setEnabled(False)
        self._log_edit.setEnabled(False)
        self._log_save_btn.setEnabled(False)
        self._preview.setText("(选择任务进行编辑)")
        self._timeline_card.setVisible(False)
        self._select_all_cb.setEnabled(False)
        self._delete_sel_btn.setEnabled(False)
        self._copy_tl_btn.setEnabled(False)
        self._clear_entries()
        self._hide_log_detail()

    def show_empty(self) -> None:
        """Show encouraging empty-state when no tasks match the current filter."""
        self._current_task = None
        self._original_md = ""
        self._md_edit.blockSignals(True)
        self._md_edit.clear()
        self._md_edit.blockSignals(False)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._status_combo.setEnabled(False)
        self._status_btn.setEnabled(False)
        self._log_edit.setEnabled(False)
        self._log_save_btn.setEnabled(False)
        self._preview.setText(
            '<div style="text-align:center;padding:20px 0;">'
            '<span style="font-size:28px;">☕</span><br>'
            '<span style="color:#888;font-size:13px;">今日无事，找点事情干一下吧</span>'
            '</div>'
        )
        self._timeline_card.setVisible(False)
        self._select_all_cb.setEnabled(False)
        self._delete_sel_btn.setEnabled(False)
        self._copy_tl_btn.setEnabled(False)
        self._clear_entries()
        self._hide_log_detail()

    def current_task(self) -> Task | None:
        return self._current_task

    def show_details(self, task: Task) -> None:
        self.load_task(task)

    def create_draft(self) -> None:
        """Create an in-memory draft TODO task with today's date. Not persisted until saved."""
        today = datetime.now().strftime("%Y-%m-%d")
        template = f"- [ ] TODO [#A] <{today}> 新任务"
        parsed = self._parser.parse(template)
        from ...models.task import Task as TaskCls

        draft = TaskCls(
            id="",  # empty ID = draft, not in DB
            raw_md=template,
            title=parsed.clean_title,
            status=parsed.status,
            priority=parsed.priority,
            tags=parsed.tags,
            scheduled_date=parsed.scheduled_date,
            deadline_date=parsed.deadline_date,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.load_task(draft)
        # In draft mode, save starts enabled because template != empty
        self._save_btn.setEnabled(True)

    def has_unsaved_draft(self) -> bool:
        """Return True if the panel holds an in-memory draft (not yet in DB)."""
        return self._current_task is not None and self._current_task.id == ""

    def discard_draft(self) -> None:
        """Discard the current draft without saving to DB."""
        if self.has_unsaved_draft():
            self.clear()

    # ------------------------------------------------------------------
    # Markdown editing
    # ------------------------------------------------------------------

    def _on_text_changed(self) -> None:
        self._update_preview()
        if self._current_task is not None:
            current_text = self._md_edit.toPlainText().strip()
            self._save_btn.setEnabled(current_text != self._original_md.strip())

    def _update_preview(self) -> None:
        text = self._md_edit.toPlainText().strip()
        if not text:
            self._preview.setText("(空)")
            return
        try:
            parsed = self._parser.parse(text)
            title = parsed.clean_title
            tags_str = " ".join(
                f"<span style='color:#5b8def;font-size:10px;'>{t}</span>"
                for t in (parsed.tags or [])
            )
            sc = parsed.status.display_color
            pc = parsed.priority.display_color

            # Status badge — same visual as left table delegate
            html = (
                f"<span style='background:{sc};color:#fff;padding:1px 7px;"
                f"border-radius:3px;font-size:10px;'>{parsed.status.display_name}</span>"
            )

            # Priority: colored dot + letter (matching left table delegate style)
            if parsed.priority.name != "NONE":
                html += (
                    f" <span style='color:{pc};font-size:11px;'>"
                    f"●{parsed.priority.name}</span>"
                )

            if parsed.scheduled_date:
                html += (
                    f" <span style='color:#888;font-size:10px;'>"
                    f"📅{parsed.scheduled_date.isoformat()}</span>"
                )
            if parsed.deadline_date:
                html += (
                    f" <span style='color:#c66;font-size:10px;'>"
                    f"⏰{parsed.deadline_date.isoformat()}</span>"
                )
            html += f" <span style='font-size:12px;'>{title}</span>"
            if tags_str:
                html += f" {tags_str}"
            self._preview.setText(html)
        except ValueError:
            self._preview.setText('<span style="color:#e74c3c;">⚠ 无法解析</span>')

    def _on_save(self) -> None:
        if not self._current_task:
            return
        text = self._md_edit.toPlainText().strip()
        if not text:
            return
        try:
            parsed = self._parser.parse(text)
        except ValueError:
            QMessageBox.warning(self, "解析失败", "Markdown 格式不正确，请检查。")
            return

        task = self._current_task
        old_status = task.status
        task.raw_md = text
        task.title = parsed.clean_title
        task.status = parsed.status
        task.priority = parsed.priority
        task.tags = parsed.tags
        task.scheduled_date = parsed.scheduled_date
        task.deadline_date = parsed.deadline_date
        task.updated_at = datetime.now()
        if task.status != old_status:
            task.activity_log.append({
                "ts": datetime.now().isoformat(),
                "content": f"状态变更: {old_status.display_name} → {task.status.display_name}",
            })
        if task.status == TaskStatus.DONE and old_status != TaskStatus.DONE:
            task.completed_at = task.deadline_date or datetime.now()
            task.activity_log.append({
                "ts": task.completed_at.isoformat(),
                "content": f"任务完成 ✓ 截止: {task.deadline_date.isoformat()}" if task.deadline_date else "任务完成 ✓",
            })

        is_draft = task.id == ""
        if is_draft:
            import uuid
            task.id = str(uuid.uuid4())
            self._repository.insert(task)
        else:
            self._repository.update(task)
        self._original_md = task.raw_md
        self._save_btn.setEnabled(False)
        if is_draft:
            self._signal_bus.task_created.emit(task)
        elif task.status != old_status:
            self._signal_bus.task_status_changed.emit(task, old_status)
        else:
            self._signal_bus.task_updated.emit(task)
        self._refresh_timeline()

    def _on_delete(self) -> None:
        if not self._current_task:
            return
        task = self._current_task
        result = QMessageBox.question(
            self, "确认删除", f'确定要删除 "{task.title}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._repository.delete(task.id)
            self._signal_bus.task_deleted.emit(task.id)
            self.clear()

    def _on_copy(self) -> None:
        if self._current_task:
            QApplication.clipboard().setText(self._current_task.raw_md)

    # ------------------------------------------------------------------
    # Quick status change
    # ------------------------------------------------------------------

    def _on_quick_status_change(self) -> None:
        if not self._current_task:
            return
        new_status = self._status_combo.currentData()
        if new_status is None or new_status == self._current_task.status:
            return
        task = self._current_task
        old_status = task.status
        task.status = new_status
        if new_status == TaskStatus.DONE:
            task.completed_at = task.deadline_date or datetime.now()
            task.activity_log.append({
                "ts": task.completed_at.isoformat(),
                "content": f"任务完成 ✓ 截止: {task.deadline_date.isoformat()}" if task.deadline_date else "任务完成 ✓",
            })
        task.raw_md = self._formatter.format(task)
        task.updated_at = datetime.now()
        task.activity_log.append({
            "ts": datetime.now().isoformat(),
            "content": f"状态切换: {old_status.display_name} → {new_status.display_name}",
        })
        self._repository.update(task)
        self._original_md = task.raw_md
        self._signal_bus.task_status_changed.emit(task, old_status)
        self._md_edit.blockSignals(True)
        self._md_edit.setText(task.raw_md)
        self._md_edit.blockSignals(False)
        self._save_btn.setEnabled(False)
        self._update_preview()
        self._refresh_timeline()

    # ==================================================================
    # Timeline — card-style entries
    # ==================================================================

    def _clear_entries(self) -> None:
        while self._entry_layout.count() > 1:
            item = self._entry_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._entry_widgets.clear()

    def _refresh_timeline(self) -> None:
        task = self._current_task
        self._clear_entries()
        self._hide_log_detail()
        if not task:
            self._entry_scroll.setVisible(False)
            self._entry_placeholder.setVisible(True)
            self._select_all_cb.setEnabled(False)
            self._delete_sel_btn.setEnabled(False)
            self._copy_tl_btn.setEnabled(False)
            return

        self._entry_placeholder.setVisible(False)
        self._entry_scroll.setVisible(True)
        self._select_all_cb.setEnabled(True)
        self._select_all_cb.setCheckState(Qt.CheckState.Unchecked)
        self._copy_tl_btn.setEnabled(True)

        entries = self._build_entries(task)

        # Find latest user entry for auto-expand
        latest_user_entry: dict | None = None
        for e in entries:
            if e.get("source") == "user":
                latest_user_entry = e
                break

        for e in entries:
            card = _TimelineEntryWidget(e)
            card.clicked.connect(self._on_entry_clicked)
            card.checked_changed.connect(self._on_entry_checked_changed)
            self._entry_layout.insertWidget(self._entry_layout.count() - 1, card)
            self._entry_widgets.append(card)

        if latest_user_entry:
            self._select_entry(latest_user_entry)
        else:
            self._reset_log_editor()

        self._update_delete_sel_btn()

    def _build_entries(self, task: Task) -> list[dict]:
        """Build timeline entry list, newest first."""
        entries: list[dict] = []

        entries.append({
            "ts": datetime.now().isoformat(),
            "content": f"当前: {task.status.display_name}",
            "icon": "▶",
            "color": task.status.display_color,
            "source": "system",
        })

        if task.completed_at:
            entries.append({
                "ts": task.completed_at.isoformat(),
                "content": "任务完成 ✓",
                "icon": "●",
                "color": "#27ae60",
                "source": "system",
            })

        for e in reversed(task.activity_log):
            is_status = "状态" in e.get("content", "")
            entries.append({
                "ts": e.get("ts", ""),
                "content": e.get("content", ""),
                "icon": "●",
                "color": "#f39c12",
                "source": "system" if is_status else "user",
            })

        entries.append({
            "ts": task.created_at.isoformat() if task.created_at else "",
            "content": "创建任务",
            "icon": "○",
            "color": "#aaa",
            "source": "system",
        })

        return entries

    # ------------------------------------------------------------------
    # Entry selection → unified log editor (merged detail + progress)
    # ------------------------------------------------------------------

    def _on_entry_clicked(self, entry: dict) -> None:
        self._select_entry(entry)

    def _select_entry(self, entry: dict) -> None:
        self._selected_entry = entry
        for w in self._entry_widgets:
            w.set_selected(w.entry is entry)

        source = entry.get("source", "system")
        content = entry.get("content", "")
        is_system = source == "system"

        if is_system:
            self._log_editor_label.setText("查看详情")
            self._log_edit.blockSignals(True)
            self._log_edit.setPlainText(content)
            self._log_edit.blockSignals(False)
            self._log_edit.setReadOnly(True)
            self._log_edit.setStyleSheet("QTextEdit { background: #f5f4f0; color: #888; }")
            self._log_save_btn.setVisible(False)
            self._log_delete_btn.setVisible(False)
            self._log_cancel_btn.setVisible(True)
            self._log_cancel_btn.setEnabled(True)
        else:
            self._log_editor_label.setText("编辑日志")
            self._log_edit.blockSignals(True)
            self._log_edit.setPlainText(content)
            self._log_edit.blockSignals(False)
            self._log_edit.setReadOnly(False)
            self._log_edit.setStyleSheet("")
            self._log_save_btn.setText("保存修改")
            self._log_save_btn.setVisible(True)
            self._log_save_btn.setEnabled(True)
            self._log_delete_btn.setVisible(True)
            self._log_delete_btn.setEnabled(True)
            self._log_cancel_btn.setVisible(True)
            self._log_cancel_btn.setEnabled(True)

    def _hide_log_detail(self) -> None:
        """Return to default 'add progress' mode."""
        self._selected_entry = None
        for w in self._entry_widgets:
            w.set_selected(False)
        self._reset_log_editor()

    def _reset_log_editor(self) -> None:
        self._selected_entry = None
        self._log_editor_label.setText("追加进展")
        self._log_edit.blockSignals(True)
        self._log_edit.clear()
        self._log_edit.blockSignals(False)
        self._log_edit.setReadOnly(False)
        self._log_edit.setStyleSheet("")
        self._log_edit.setPlaceholderText("输入进展内容…")
        self._log_save_btn.setText("追加进展")
        self._log_save_btn.setVisible(True)
        self._log_save_btn.setEnabled(True)
        self._log_delete_btn.setVisible(False)
        self._log_delete_btn.setEnabled(False)
        self._log_cancel_btn.setVisible(False)
        self._log_cancel_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Log editor actions
    # ------------------------------------------------------------------

    def _on_log_save(self) -> None:
        content = self._log_edit.toPlainText().strip()
        if not content:
            return

        if self._selected_entry and self._selected_entry.get("source") == "user":
            # Editing an existing user entry
            self._on_detail_save()
        else:
            # Adding new progress
            self._on_add_progress()

    def _on_log_delete(self) -> None:
        if not self._current_task or not self._selected_entry:
            return
        self._on_detail_delete()

    def _on_log_cancel(self) -> None:
        self._hide_log_detail()

    # ------------------------------------------------------------------
    # Add progress
    # ------------------------------------------------------------------

    def _on_add_progress(self) -> None:
        if not self._current_task:
            return
        content = self._log_edit.toPlainText().strip()
        if not content:
            return
        entry = {"ts": datetime.now().isoformat(), "content": content}
        task = self._current_task
        task.activity_log.append(entry)
        task.updated_at = datetime.now()
        self._repository.update(task)
        self._signal_bus.task_updated.emit(task)
        self._refresh_timeline()

    # ------------------------------------------------------------------
    # Edit / delete existing entry
    # ------------------------------------------------------------------

    def _on_detail_save(self) -> None:
        if not self._current_task or not self._selected_entry:
            return
        new_content = self._log_edit.toPlainText().strip()
        if not new_content:
            return
        task = self._current_task
        old_ts = self._selected_entry.get("ts", "")
        old_content = self._selected_entry.get("content", "")
        for e in task.activity_log:
            if e.get("ts") == old_ts and e.get("content") == old_content:
                e["content"] = new_content
                break
        task.updated_at = datetime.now()
        self._repository.update(task)
        self._signal_bus.task_updated.emit(task)
        self._refresh_timeline()

    def _on_detail_delete(self) -> None:
        if not self._current_task or not self._selected_entry:
            return
        task = self._current_task
        old_ts = self._selected_entry.get("ts", "")
        old_content = self._selected_entry.get("content", "")

        result = QMessageBox.question(
            self, "确认删除", "确定要删除此条日志吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        task.activity_log = [
            e for e in task.activity_log
            if not (e.get("ts") == old_ts and e.get("content") == old_content)
        ]
        task.updated_at = datetime.now()
        self._repository.update(task)
        self._signal_bus.task_updated.emit(task)
        self._refresh_timeline()

    # ------------------------------------------------------------------
    # Multi-select
    # ------------------------------------------------------------------

    def _on_select_all_changed(self, state: int) -> None:
        checked = state == Qt.CheckState.Checked.value
        for w in self._entry_widgets:
            w.set_checked(checked)
        self._update_delete_sel_btn()

    def _on_entry_checked_changed(self) -> None:
        self._update_delete_sel_btn()
        all_checked = all(w.is_checked for w in self._entry_widgets)
        any_checked = any(w.is_checked for w in self._entry_widgets)
        self._select_all_cb.blockSignals(True)
        if all_checked:
            self._select_all_cb.setCheckState(Qt.CheckState.Checked)
        elif any_checked:
            self._select_all_cb.setCheckState(Qt.CheckState.PartiallyChecked)
        else:
            self._select_all_cb.setCheckState(Qt.CheckState.Unchecked)
        self._select_all_cb.blockSignals(False)

    def _update_delete_sel_btn(self) -> None:
        any_checked = any(w.is_checked for w in self._entry_widgets)
        self._delete_sel_btn.setEnabled(any_checked)

    def _on_delete_selected(self) -> None:
        if not self._current_task:
            return
        selected = [w.entry for w in self._entry_widgets if w.is_checked]
        if not selected:
            return
        count = len(selected)
        result = QMessageBox.question(
            self, "确认删除", f"确定要删除选中的 {count} 条日志吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        task = self._current_task
        remove_keys = {(e.get("ts"), e.get("content")) for e in selected}
        task.activity_log = [
            e for e in task.activity_log
            if (e.get("ts"), e.get("content")) not in remove_keys
        ]
        task.updated_at = datetime.now()
        self._repository.update(task)
        self._signal_bus.task_updated.emit(task)
        self._refresh_timeline()

    # ------------------------------------------------------------------
    # Copy timeline as Markdown
    # ------------------------------------------------------------------

    def _on_copy_timeline_md(self) -> None:
        if not self._current_task:
            return
        task = self._current_task
        lines: list[str] = [f"## 活动时间线 — {task.title}", ""]

        if task.created_at:
            lines.append(f"- {task.created_at.strftime('%Y-%m-%d %H:%M')} 创建任务")

        for e in task.activity_log:
            ts = e.get("ts", "")
            content = e.get("content", "")
            try:
                dt_ts = datetime.fromisoformat(ts) if ts else None
                ts_str = dt_ts.strftime("%Y-%m-%d %H:%M") if dt_ts else ts
            except (ValueError, TypeError):
                ts_str = ts[:16] if ts else "—"
            lines.append(f"- {ts_str} {content}")

        if task.completed_at:
            lines.append(f"- {task.completed_at.strftime('%Y-%m-%d %H:%M')} 任务完成 ✓")

        QApplication.clipboard().setText("\n".join(lines))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _h_sep() -> QWidget:
    w = QWidget()
    w.setFixedHeight(1)
    w.setStyleSheet("background: #e8e6e0; border: none;")
    return w


def _fmt_ts(ts, short: bool = False) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return ts[:16]
    if short:
        return ts.strftime("%m-%d %H:%M")
    return ts.strftime("%Y-%m-%d %H:%M")
