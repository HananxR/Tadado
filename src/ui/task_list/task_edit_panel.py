"""Inline task editor panel with card-style timeline, detail editing, and multi-select."""

from __future__ import annotations

import re

from datetime import date, datetime, timedelta
from typing import Callable

from PySide6.QtCore import QDate, QSize, QTime, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QBrush, QColor, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

import sys
from pathlib import Path as _Path

from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ...utils.signal_bus import get_signal_bus


def _welcome_bg_path() -> str:
    """Resolve the welcome banner background image path."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = _Path(base) / "resources" / "welcome_bg.jpg"
    else:
        p = _Path(__file__).resolve().parents[3] / "resources" / "welcome_bg.jpg"
    return p.as_posix() if p.exists() else ""


# ---------------------------------------------------------------------------
# Per-entry card widget in the timeline
# ---------------------------------------------------------------------------


class _TimelineEntryWidget(QWidget):
    """One card in the timeline: icon + timestamp + content (compact, fixed height)."""

    clicked = Signal(dict)

    def __init__(self, entry: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry
        self._selected = False

        self.setObjectName("entryCard")
        self.setFixedHeight(48)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(6)

        # Icon dot
        icon = entry.get("icon", "●")
        color = entry.get("color", "#aaa")
        dot = QLabel(
            f'<span style="color:{color};font-weight:bold;font-size:12px;">{icon}</span>'
        )
        dot.setFixedWidth(16)
        dot.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(dot)

        # Timestamp + content
        right = QVBoxLayout()
        right.setSpacing(1)
        ts = _fmt_ts(entry.get("ts", ""), short=True)
        ts_label = QLabel(f'<span style="color:{color};font-size:10px;">{ts}</span>')
        ts_label.setTextFormat(Qt.TextFormat.RichText)
        right.addWidget(ts_label)

        content = entry.get("content", "")
        content_label = QLabel(content)
        content_label.setWordWrap(False)
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

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


# ---------------------------------------------------------------------------
# Timeline browser with click-to-edit support
# ---------------------------------------------------------------------------


class _TimelineBrowser(QTextBrowser):
    """QTextBrowser subclass that detects clicks on individual timeline entries."""

    entry_clicked = Signal(int)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            anchor = self.anchorAt(event.pos())
            if anchor.startswith("entry:"):
                try:
                    idx = int(anchor.split(":", 1)[1])
                    self.entry_clicked.emit(idx)
                    return
                except (ValueError, IndexError):
                    pass
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Banner widget with background image + text overlay
# ---------------------------------------------------------------------------


class _BannerWidget(QWidget):
    """A banner that paints a background image with semi-transparent overlay + HTML text."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bg_pixmap: QPixmap | None = None
        self._html: str = ""
        self._scaled_bg: QPixmap | None = None
        self.setMinimumHeight(120)

    def set_html(self, html: str) -> None:
        self._html = html
        self.update()

    def set_bg_pixmap(self, pixmap: QPixmap) -> None:
        self._bg_pixmap = pixmap if not pixmap.isNull() else None
        self._scaled_bg = None
        self.update()

    def resizeEvent(self, event) -> None:
        self._scaled_bg = None
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background image (or solid fallback)
        if self._bg_pixmap:
            if self._scaled_bg is None:
                self._scaled_bg = self._bg_pixmap.scaled(
                    w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            p.drawPixmap(0, 0, self._scaled_bg)
        else:
            p.setBrush(QBrush(QColor("#fffdf7")))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(0, 0, w, h)

        # Render HTML text centered both horizontally and vertically
        if self._html:
            doc = QTextDocument()
            doc.setHtml(
                f'<p align="center" style="margin:0;line-height:1.4;">'
                f'{self._html}</p>'
            )
            doc.setTextWidth(w - 30)
            doc.setDocumentMargin(0)
            th = doc.size().height()
            ty = max(0, (h - int(th)) // 2)
            p.save()
            p.translate(15, ty)
            doc.drawContents(p)
            p.restore()
        p.end()


# ---------------------------------------------------------------------------
# Main edit panel
# ---------------------------------------------------------------------------


class TaskEditPanel(QWidget):
    """Right-side panel: raw_md editor, preview, save/delete, and card-style activity timeline."""

    def __init__(self, repository: TaskRepository, task_model=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._repository = repository
        self._task_model = task_model  # for in-place row updates
        self._parser = MarkdownTaskParser()
        self._formatter = MarkdownTaskFormatter()
        self._signal_bus = get_signal_bus()
        self._current_task: Task | None = None
        self._original_md: str = ""
        self._entry_widgets: list[_TimelineEntryWidget] = []
        self._selected_entry: dict | None = None
        self._draft_partition_id: str | None = None
        self._updating_from_md: bool = False

        self.setObjectName("taskEditPanel")
        self.setMinimumWidth(320)

        # Preload welcome background
        self._welcome_pixmap = QPixmap(_welcome_bg_path()) if _welcome_bg_path() else QPixmap()

        # Direct layout (headers fixed, timeline scrolls internally)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(6)

        # --- Draft banner ---
        self._draft_banner = _BannerWidget()
        self._draft_banner.setVisible(False)
        layout.addWidget(self._draft_banner, 6)

        # --- 编辑任务 section ---
        editor_header = QLabel("编辑任务")
        editor_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(editor_header)
        # Collapse toggle next to header
        self._collapse_btn = QPushButton("▼")
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setStyleSheet("font-size: 10px; padding: 0;")
        self._collapse_btn.setToolTip("折叠编辑区")
        self._collapse_btn.clicked.connect(self._on_toggle_collapse)
        self._collapse_btn.setVisible(False)
        # (Button will be positioned in layout after header)

        # Collapsible editor content
        self._editor_collapsible = QWidget()
        ec = QVBoxLayout(self._editor_collapsible)
        ec.setContentsMargins(0, 0, 0, 0)
        ec.setSpacing(4)

        ec.addWidget(QLabel("Markdown："))
        self._md_edit = QTextEdit()
        self._md_edit.setObjectName("mdEditor")
        self._md_edit.setPlaceholderText("- [ ] TODO <2026-05-20> 标题 #标签")
        self._md_edit.setMaximumHeight(85)
        self._md_edit.textChanged.connect(self._on_text_changed)
        ec.addWidget(self._md_edit)

        ec.addWidget(QLabel("预览："))
        self._preview = QLabel("(选择任务进行编辑)")
        self._preview.setTextFormat(Qt.TextFormat.RichText)
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet(
            "QLabel { color: #555; background: #f8f8f8; padding: 6px 8px;"
            " border-radius: 4px; font-size: 12px; }"
        )
        self._preview.setMinimumHeight(36)
        self._preview.setMaximumHeight(52)
        ec.addWidget(self._preview)

        # Date / time metadata
        meta_widget = QWidget()
        meta_widget.setStyleSheet("background: transparent;")
        meta_layout = QVBoxLayout(meta_widget)
        meta_layout.setContentsMargins(0, 2, 0, 2)
        meta_layout.setSpacing(4)
        created_row = QHBoxLayout()
        created_row.setSpacing(6)
        created_row.addWidget(QLabel("创建时间："))
        self._created_label = QLabel("—")
        self._created_label.setStyleSheet("color: #888; font-size: 11px;")
        created_row.addWidget(self._created_label)
        created_row.addStretch()
        meta_layout.addLayout(created_row)
        deadline_row = QHBoxLayout()
        deadline_row.setSpacing(6)
        deadline_row.addWidget(QLabel("截止时间："))
        self._deadline_date_edit = QDateEdit()
        self._deadline_date_edit.setCalendarPopup(True)
        self._deadline_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._deadline_date_edit.setDate(QDate.currentDate())
        self._deadline_date_edit.setMinimumDate(QDate(2000, 1, 1))
        self._deadline_date_edit.setMaximumDate(QDate(2100, 12, 31))
        self._deadline_date_edit.setFixedWidth(138)
        self._deadline_date_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._deadline_date_edit.dateChanged.connect(self._on_deadline_picker_changed)
        deadline_row.addWidget(self._deadline_date_edit)
        self._deadline_time_edit = QTimeEdit()
        self._deadline_time_edit.setDisplayFormat("HH:mm")
        self._deadline_time_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._deadline_time_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._deadline_time_edit.timeChanged.connect(self._on_deadline_picker_changed)
        deadline_row.addWidget(self._deadline_time_edit)
        self._time_toggle = QCheckBox("时间")
        self._time_toggle.setChecked(True)
        self._time_toggle.setStyleSheet("font-size: 10px; color: #888;")
        self._time_toggle.toggled.connect(self._on_time_toggle_changed)
        deadline_row.addWidget(self._time_toggle)
        deadline_row.addStretch()
        meta_layout.addLayout(deadline_row)
        ec.addWidget(meta_widget)
        layout.addWidget(self._editor_collapsible)

        # Task summary (visible when collapsed)
        self._task_summary = QLabel()
        self._task_summary.setTextFormat(Qt.TextFormat.RichText)
        self._task_summary.setWordWrap(True)
        self._task_summary.setStyleSheet(
            "QLabel { color: #444; font-size: 12px; padding: 4px 0;"
            " background: transparent; }"
        )
        self._task_summary.setVisible(False)
        layout.addWidget(self._task_summary)

        # Action buttons
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
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addWidget(self._collapse_btn)
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

        # -- Section header --
        tl_header = QLabel("活动时间线")
        tl_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #444;")
        tc.addWidget(tl_header)

        # -- Timeline log (rich text with aligned timestamps) --
        self._timeline_log = _TimelineBrowser()
        self._timeline_log.setReadOnly(True)
        self._timeline_log.setMinimumHeight(120)
        self._timeline_log.setMaximumHeight(350)
        self._timeline_log.setStyleSheet(
            "QTextBrowser { background: #fafaf8; border: 1px solid #ddd9d0;"
            " border-radius: 6px; font-size: 12px; padding: 6px; color: #444; }"
        )
        self._entry_placeholder = QLabel("  (选择任务查看活动时间线)")
        self._entry_placeholder.setStyleSheet("color: #aaa; font-size: 11px; padding: 8px;")
        self._entry_placeholder.setVisible(False)
        tc.addWidget(self._entry_placeholder)
        self._timeline_log.entry_clicked.connect(self._on_timeline_entry_clicked)
        tc.addWidget(self._timeline_log)
        self._timeline_log.setVisible(False)

        # -- Progress input (status combo + text + button) --
        progress_label = QLabel("追加进展")
        progress_label.setStyleSheet("font-size: 11px; color: #888; font-weight: bold;")
        tc.addWidget(progress_label)

        self._log_edit = QTextEdit()
        self._log_edit.setPlaceholderText("输入进展内容…")
        self._log_edit.setMinimumHeight(46)
        self._log_edit.setMaximumHeight(72)
        self._log_edit.setEnabled(False)
        tc.addWidget(self._log_edit)

        progress_btn_row = QHBoxLayout()
        progress_btn_row.setSpacing(6)
        self._status_combo = QComboBox()
        for s in (TaskStatus.URGENT, TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE):
            self._status_combo.addItem(f"● {s.display_name}", s)
            from PySide6.QtGui import QColor
            self._status_combo.setItemData(
                self._status_combo.count() - 1,
                QColor(s.display_color),
                Qt.ItemDataRole.ForegroundRole,
            )
        self._status_combo.setEnabled(False)
        self._status_combo.setFixedWidth(90)
        progress_btn_row.addWidget(self._status_combo)

        self._progress_spin = QSpinBox()
        self._progress_spin.setRange(0, 100)
        self._progress_spin.setValue(0)
        self._progress_spin.setSuffix("%")
        self._progress_spin.setFixedWidth(62)
        self._progress_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_spin.setEnabled(False)
        progress_btn_row.addWidget(self._progress_spin)

        self._log_save_btn = QPushButton("追加进展")
        self._log_save_btn.setObjectName("saveBtn")
        self._log_save_btn.clicked.connect(self._on_log_save)
        self._log_save_btn.setEnabled(False)
        progress_btn_row.addWidget(self._log_save_btn)
        progress_btn_row.addStretch()
        tc.addLayout(progress_btn_row)

        layout.addWidget(self._timeline_card, 6)
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

        self._draft_banner.setVisible(False)
        self._collapse_btn.setVisible(True)
        self._editor_collapsible.setVisible(False)  # default collapsed
        self._collapse_btn.setText("▼")
        # Show task summary when collapsed
        self._task_summary.setText(f'任务：<b>{task.title}</b>')
        self._task_summary.setVisible(True)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(True)
        self._status_combo.setEnabled(True)
        self._log_edit.setEnabled(True)
        self._log_save_btn.setEnabled(True)
        self._timeline_card.setVisible(True)


        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == task.status:
                self._status_combo.setCurrentIndex(i)
                break

        # Set date/time pickers
        self._updating_from_md = True
        if task.deadline_date:
            qd = QDate(task.deadline_date.year, task.deadline_date.month, task.deadline_date.day)
            self._deadline_date_edit.setDate(qd)
            self._time_toggle.setChecked(True)
            if task.deadline_time:
                h, m = task.deadline_time.split(":")
                self._deadline_time_edit.setTime(QTime(int(h), int(m)))
            else:
                self._deadline_time_edit.setTime(QTime(23, 59))
        else:
            self._deadline_date_edit.setDate(QDate.currentDate())
            self._time_toggle.setChecked(True)
            self._deadline_time_edit.setTime(QTime(23, 59))
        self._updating_from_md = False

        # Set created_at label
        if task.created_at:
            self._created_label.setText(task.created_at.strftime("%Y-%m-%d %H:%M"))
        else:
            self._created_label.setText("—")

        self._progress_spin.setValue(task.progress)
        self._progress_spin.setEnabled(True)
        self._update_preview()
        self._refresh_timeline()
        self._reset_log_editor()

    def clear(self) -> None:
        self._current_task = None
        self._original_md = ""
        self._md_edit.blockSignals(True)
        self._md_edit.clear()
        self._md_edit.blockSignals(False)
        self._collapse_btn.setVisible(False)
        self._editor_collapsible.setVisible(True)
        self._task_summary.setVisible(False)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._status_combo.setEnabled(False)
        self._log_edit.setEnabled(False)
        self._log_save_btn.setEnabled(False)
        self._draft_banner.setVisible(False)
        self._preview.setText("(选择任务进行编辑)")
        self._timeline_card.setVisible(False)

        self._updating_from_md = True
        self._deadline_date_edit.setDate(QDate.currentDate())
        self._time_toggle.setChecked(True)
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._created_label.setText("—")
        self._updating_from_md = False
        self._clear_entries()
        self._hide_log_detail()

    def show_empty(self) -> None:
        """Show encouraging empty-state — 60% banner + 40% editor."""
        self._current_task = None
        self._original_md = ""
        html = (
            '<span style="font-size:12px;color:#c0392b;letter-spacing:4px;">'
            '─ 宜 ─</span><br>'
            '<span style="font-size:28px;">🎉</span><br>'
            '<span style="font-size:20px;color:#c0392b;font-weight:bold;">'
            '今日无事</span><br>'
            '<span style="font-size:13px;color:#eee;letter-spacing:2px;">'
            '宜狂欢 · 忌加班</span><br>'
            '<span style="font-size:12px;color:#c0392b;letter-spacing:4px;">'
            '─ 忌 ─</span>'
        )
        self._draft_banner.set_html(html)
        self._draft_banner.set_bg_pixmap(self._welcome_pixmap)
        self._draft_banner.setVisible(True)
        # Editor section (40%)
        self._md_edit.blockSignals(True)
        self._md_edit.setText("")
        self._md_edit.setPlaceholderText("- [ ] TODO <2026-05-20> 标题 #标签")
        self._md_edit.blockSignals(False)
        self._collapse_btn.setVisible(False)
        self._editor_collapsible.setVisible(True)
        self._task_summary.setVisible(False)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._status_combo.setEnabled(True)
        self._log_edit.setEnabled(True)
        self._log_save_btn.setEnabled(True)
        self._preview.setText("")
        self._timeline_card.setVisible(False)

        self._updating_from_md = True
        self._deadline_date_edit.setDate(QDate.currentDate())
        self._time_toggle.setChecked(True)
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._created_label.setText("—")
        self._updating_from_md = False
        self._progress_spin.setValue(0)
        self._progress_spin.setEnabled(False)
        self._clear_entries()
        self._hide_log_detail()

    def current_task(self) -> Task | None:
        return self._current_task

    def show_details(self, task: Task) -> None:
        self.load_task(task)

    def set_active_partition(self, partition_id: str | None) -> None:
        """Set the partition for the next draft task."""
        self._draft_partition_id = partition_id

    def create_draft(self) -> None:
        """Create an in-memory draft TODO task defaulting deadline to nearest Friday."""
        today_d = date.today()
        weekday = today_d.isoweekday()
        days_ahead = (5 - weekday) % 7
        if days_ahead == 0:
            days_ahead = 7
        target = today_d + timedelta(days=days_ahead)
        friday_str = target.strftime("%Y-%m-%d")
        template = f"- [ ] TODO <{friday_str}> 新任务"
        parsed = self._parser.parse(template)
        from ...models.task import Task as TaskCls

        draft = TaskCls(
            id="",  # empty ID = draft, not in DB
            raw_md=template,
            title=parsed.clean_title,
            status=parsed.status,
            tags=parsed.tags,
            scheduled_date=parsed.scheduled_date,
            deadline_date=parsed.deadline_date,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        # Load draft into editor without showing full timeline
        self._current_task = draft
        self._original_md = ""
        self._md_edit.blockSignals(True)
        self._md_edit.setText(template)
        self._md_edit.blockSignals(False)

        html = (
            '<span style="font-size:12px;color:#c0392b;letter-spacing:4px;">'
            '─ 宜 ─</span><br>'
            '<span style="font-size:28px;">✍️</span><br>'
            '<span style="font-size:20px;color:#c0392b;font-weight:bold;">'
            '今日无事</span><br>'
            '<span style="font-size:13px;color:#eee;letter-spacing:2px;">'
            '宜创作 · 忌虚度</span><br>'
            '<span style="font-size:12px;color:#c0392b;letter-spacing:4px;">'
            '─ 忌 ─</span>'
        )
        self._draft_banner.set_html(html)
        self._draft_banner.set_bg_pixmap(self._welcome_pixmap)
        self._draft_banner.setVisible(True)
        self._collapse_btn.setVisible(False)
        self._editor_collapsible.setVisible(True)
        self._task_summary.setVisible(False)
        # Focus editor and flash it to draw attention
        self._md_edit.setFocus()
        self._md_edit.selectAll()
        self._md_edit.setStyleSheet(
            "QTextEdit#mdEditor { border: 2px solid #5b8def; background: #f0f4ff; }"
        )
        QTimer.singleShot(800, lambda: self._md_edit.setStyleSheet(""))
        self._save_btn.setEnabled(True)
        self._delete_btn.setEnabled(False)
        # Reset status combo to TODO for new draft
        for i in range(self._status_combo.count()):
            if self._status_combo.itemData(i) == TaskStatus.TODO:
                self._status_combo.setCurrentIndex(i)
                break
        self._status_combo.setEnabled(True)
        self._progress_spin.setValue(0)
        self._progress_spin.setEnabled(True)
        self._timeline_card.setVisible(False)
        self._timeline_log.clear()
        # Set pickers for draft — deadline defaults to nearest Friday
        self._updating_from_md = True
        self._deadline_date_edit.setDate(QDate(target.year, target.month, target.day))
        self._time_toggle.setChecked(True)
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._updating_from_md = False
        self._created_label.setText(
            draft.created_at.strftime("%Y-%m-%d %H:%M") if draft.created_at else "—"
        )
        self._update_preview()
        self._clear_entries()

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
        self._sync_pickers_from_md()
        if self._current_task is not None:
            current_text = self._md_edit.toPlainText().strip()
            self._save_btn.setEnabled(current_text != self._original_md.strip())
        else:
            # Empty / welcome state: enable save if user typed something
            self._save_btn.setEnabled(bool(self._md_edit.toPlainText().strip()))

    def _sync_pickers_from_md(self) -> None:
        """Update date/time pickers from the current Markdown text."""
        if self._updating_from_md:
            return
        text = self._md_edit.toPlainText().strip()
        if not text:
            return
        try:
            parsed = self._parser.parse(text)
        except ValueError:
            return
        self._updating_from_md = True
        if parsed.deadline_date:
            qdate = QDate(parsed.deadline_date.year, parsed.deadline_date.month, parsed.deadline_date.day)
            self._deadline_date_edit.blockSignals(True)
            self._deadline_date_edit.setDate(qdate)
            self._deadline_date_edit.blockSignals(False)
            self._time_toggle.setChecked(True)
            if parsed.deadline_time:
                h, m = parsed.deadline_time.split(":")
                self._deadline_time_edit.blockSignals(True)
                self._deadline_time_edit.setTime(QTime(int(h), int(m)))
                self._deadline_time_edit.blockSignals(False)
            else:
                self._deadline_time_edit.setTime(QTime(23, 59))
        else:
            self._deadline_date_edit.blockSignals(True)
            self._deadline_date_edit.setDate(QDate.currentDate())
            self._deadline_date_edit.blockSignals(False)
            self._time_toggle.setChecked(True)
            self._deadline_time_edit.setTime(QTime(23, 59))
        self._updating_from_md = False

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

            # Status badge — same visual as left table delegate
            html = (
                f"<span style='background:{sc};color:#fff;padding:1px 7px;"
                f"border-radius:3px;font-size:10px;'>{parsed.status.display_name}</span>"
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

    # ------------------------------------------------------------------
    # Deadline picker → Markdown sync
    # ------------------------------------------------------------------

    def _on_deadline_picker_changed(self) -> None:
        """Update Markdown text when the date/time pickers change."""
        if self._updating_from_md or not self._current_task:
            return
        self._updating_from_md = True
        text = self._md_edit.toPlainText().strip()
        if not text:
            self._updating_from_md = False
            return
        qdate = self._deadline_date_edit.date()
        new_date = qdate.toString("yyyy-MM-dd")
        # Replace or add deadline in the Markdown
        import re as _re
        # Match existing deadline pattern <YYYY-MM-DD> or <YYYY-MM-DD HH:MM>
        dl_pattern = _re.compile(r"<(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2})?>")
        if self._time_toggle.isChecked():
            qt = self._deadline_time_edit.time()
            new_dl = f"<{new_date} {qt.toString('HH:mm')}>"
        else:
            new_dl = f"<{new_date}>"
        if dl_pattern.search(text):
            text = dl_pattern.sub(new_dl, text, count=1)
        else:
            # No deadline in text — insert before the title
            parts = text.rsplit(" ", 1) if " " in text else [text, ""]
            # Insert deadline before last part (title)
            idx = text.rfind(">")
            if idx >= 0:
                text = text[:idx + 1] + " " + new_dl + text[idx + 1:]
            else:
                # Insert after status keyword
                kw_match = _re.search(r"(TODO|DOING|DONE|URGENT|WAIT|LATER)\s*", text)
                if kw_match:
                    pos = kw_match.end()
                    text = text[:pos] + f"{new_dl} " + text[pos:]
                else:
                    text = text.rstrip() + " " + new_dl
        self._md_edit.blockSignals(True)
        self._md_edit.setText(text)
        self._md_edit.blockSignals(False)
        self._update_preview()
        if self._current_task is not None:
            current_text = self._md_edit.toPlainText().strip()
            self._save_btn.setEnabled(current_text != self._original_md.strip())
        self._updating_from_md = False

    def _on_time_toggle_changed(self, checked: bool) -> None:
        """Show or hide the time editor."""
        self._deadline_time_edit.setVisible(checked)
        if not self._updating_from_md:
            self._on_deadline_picker_changed()

    def _on_save(self) -> None:
        is_new = self._current_task is None
        if is_new:
            # Creating a new task from empty/welcome state
            import uuid
            from ...models.task import Task as TaskCls
            self._current_task = TaskCls(
                id="",
                raw_md="",
                title="",
                status=TaskStatus.TODO,
                tags=[],
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
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
        # Status is controlled by the combo, not Markdown text
        combo_status = self._status_combo.currentData()
        task.title = parsed.clean_title
        task.status = combo_status if combo_status else parsed.status
        task.tags = parsed.tags
        task.scheduled_date = parsed.scheduled_date
        task.deadline_date = parsed.deadline_date
        task.deadline_time = parsed.deadline_time
        # Regenerate canonical raw_md with combo status
        task.raw_md = self._formatter.format(task)
        task.updated_at = datetime.now()
        if task.status != old_status:
            if task.status == TaskStatus.DONE:
                task.completed_at = task.deadline_date or datetime.now()
                task.activity_log.append({
                    "ts": task.completed_at.isoformat(),
                    "content": f"任务完成 ✓ 截止: {task.deadline_date.isoformat()}" if task.deadline_date else "任务完成 ✓",
                    "status": task.status.value,
            })
            else:
                task.activity_log.append({
                    "ts": datetime.now().isoformat(),
                    "content": f"状态变更: {old_status.display_name} → {task.status.display_name}",
                    "status": task.status.value,
                })

        is_draft = task.id == ""
        if is_draft:
            import uuid
            task.id = str(uuid.uuid4())
            if self._draft_partition_id:
                task.partition_id = self._draft_partition_id
            self._repository.insert(task)
        else:
            self._repository.update(task)
        self._original_md = task.raw_md
        self._save_btn.setEnabled(False)
        # Update editor with canonical Markdown
        self._md_edit.blockSignals(True)
        self._md_edit.setText(task.raw_md)
        self._md_edit.blockSignals(False)
        self._update_preview()
        if is_draft:
            self._signal_bus.task_created.emit(task)
        elif task.status != old_status:
            self._signal_bus.task_status_changed.emit(task, old_status)
        else:
            self._signal_bus.task_updated.emit(task)
        self._refresh_timeline()
        # Collapse editor after save
        self._collapse_btn.setVisible(True)
        self._editor_collapsible.setVisible(False)
        self._collapse_btn.setText("▼")
        self._task_summary.setText(f'任务：<b>{task.title}</b>')
        self._task_summary.setVisible(True)

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

    # ------------------------------------------------------------------
    # Collapse / expand editor
    # ------------------------------------------------------------------

    def _on_toggle_collapse(self) -> None:
        collapsed = self._editor_collapsible.isVisible()
        self._editor_collapsible.setVisible(not collapsed)
        self._collapse_btn.setText("▼" if collapsed else "▲")
        self._collapse_btn.setToolTip("展开编辑区" if collapsed else "折叠编辑区")
        self._task_summary.setVisible(collapsed)

    # ------------------------------------------------------------------
    # Quick status change
    # ------------------------------------------------------------------

    # ==================================================================
    # Timeline — card-style entries
    # ==================================================================

    def _clear_entries(self) -> None:
        """Clear the timeline text log."""
        if hasattr(self, '_timeline_log'):
            self._timeline_log.clear()

    def _hide_log_detail(self) -> None:
        """Reset to add-progress mode (no-op now)."""
        self._reset_log_editor()

    def refresh_timeline(self) -> None:
        """Public: refresh timeline display without resetting editor state."""
        self._refresh_timeline()

    def _refresh_timeline(self) -> None:
        task = self._current_task
        if not task:
            self._timeline_log.setVisible(False)
            self._entry_placeholder.setVisible(True)
            return

        self._entry_placeholder.setVisible(False)
        self._timeline_log.setVisible(True)

        def _row(icon: str, color: str, ts: str, content: str, entry_idx: int | None = None) -> str:
            anchor = f'<a name="entry:{entry_idx}"></a>' if entry_idx is not None else ""
            return (
                f'<p style="margin:3px 0;font-family:Consolas,monospace;font-size:12px;">'
                f'{anchor}'
                f'<span style="color:{color};font-weight:bold;">{icon}</span>'
                f' <span style="color:{color};">{ts:>11}</span>'
                f' <span style="color:#444;">{content}</span>'
                f'</p>'
            )

        rows: list[str] = []
        for i, e in enumerate(reversed(task.activity_log)):
            orig_idx = len(task.activity_log) - 1 - i
            ts = _fmt_ts(e.get("ts", ""), True)
            content = e.get("content", "")
            st_val = e.get("status", "")
            if not st_val:
                # Legacy entry: derive status from content or use current
                if "状态切换:" in content or "状态变更:" in content:
                    m = re.search(r"→\s*(\S+)", content)
                    st_val = m.group(1) if m else task.status.value
                else:
                    st_val = task.status.value
            try:
                st = TaskStatus.from_string(st_val)
                sc = st.display_color
                sn = st.display_name
            except Exception:
                sc = "#888"
                sn = st_val
            is_done = "任务完成" in content
            color = "#27ae60" if is_done else "#f39c12"
            progress_val = e.get("progress", task.progress)
            rows.append(_row("●", color, ts,
                              f'<span style="color:{sc};">[{sn}|{progress_val}%]</span> {content}',
                              entry_idx=orig_idx))
        # Always show creation marker (oldest entry), unless a real one exists
        if task.created_at and not any("创建任务" in e.get("content", "") for e in task.activity_log):
            rows.append(_row("○", "#aaa", _fmt_ts(task.created_at.isoformat(), True),
                              "创建任务"))

        self._timeline_log.setHtml(f'<div>{"".join(rows)}</div>')
        self._reset_log_editor()

    def _on_timeline_entry_clicked(self, idx: int) -> None:
        """Populate the progress editor with the clicked timeline entry for editing."""
        if not self._current_task:
            return
        if idx < 0 or idx >= len(self._current_task.activity_log):
            return

        entry = self._current_task.activity_log[idx]
        self._selected_entry = (idx, entry)

        self._log_edit.blockSignals(True)
        self._log_edit.setText(entry.get("content", ""))
        self._log_edit.blockSignals(False)
        self._log_edit.setReadOnly(False)
        self._log_edit.setPlaceholderText("编辑进展内容…")
        self._log_edit.setStyleSheet(
            "QTextEdit { border: 2px solid #f39c12; background: #fffdf5; }"
        )

        st_val = entry.get("status", "")
        if st_val:
            try:
                st = TaskStatus.from_string(st_val)
                for i in range(self._status_combo.count()):
                    if self._status_combo.itemData(i) == st:
                        self._status_combo.setCurrentIndex(i)
                        break
            except Exception:
                pass

        progress_val = entry.get("progress", self._current_task.progress)
        self._progress_spin.setValue(progress_val)

        self._log_save_btn.setText("更新进展")



    def _reset_log_editor(self) -> None:
        self._selected_entry = None
        self._log_edit.blockSignals(True)
        self._log_edit.clear()
        self._log_edit.blockSignals(False)
        self._log_edit.setReadOnly(False)
        self._log_edit.setStyleSheet("")
        self._log_edit.setPlaceholderText("输入进展内容…")
        self._log_save_btn.setText("追加进展")
        self._log_save_btn.setVisible(True)
        self._log_save_btn.setEnabled(True)
        if self._current_task:
            self._progress_spin.setValue(self._current_task.progress)

    # ------------------------------------------------------------------
    # Log editor actions
    # ------------------------------------------------------------------

    def _on_log_save(self) -> None:
        """Add or update progress: optionally change status + record text."""
        if not self._current_task:
            return
        content = self._log_edit.toPlainText().strip()
        new_status = self._status_combo.currentData()
        task = self._current_task
        old_status = task.status

        if self._selected_entry is not None:
            # ---- Editing an existing entry ----
            idx, entry = self._selected_entry
            if not content:
                self._refresh_timeline()
                return
            entry["content"] = content
            entry["status"] = new_status.value if new_status else entry.get("status", "")
            entry["progress"] = self._progress_spin.value()
            task.progress = self._progress_spin.value()
            if new_status and new_status != old_status:
                task.status = new_status
                if new_status == TaskStatus.DONE:
                    task.completed_at = task.deadline_date or datetime.now()
                task.raw_md = self._formatter.format(task)
            task.updated_at = datetime.now()
            self._repository.update(task)
            self._original_md = task.raw_md
            if self._task_model:
                self._task_model.update_task(task)
            if task.status != old_status:
                self._signal_bus.task_status_changed.emit(task, old_status)
            else:
                self._signal_bus.task_updated.emit(task)
            self._log_edit.clear()
            self._refresh_timeline()
            return

        # ---- Appending a new entry ----
        if not content and new_status == old_status:
            return  # nothing changed
        if new_status and new_status != old_status:
            task.status = new_status
            if new_status == TaskStatus.DONE:
                task.completed_at = task.deadline_date or datetime.now()
            task.raw_md = self._formatter.format(task)
        # Record one entry with current status
        entry_content = content if content else f"状态变更为 {task.status.display_name}"
        task.progress = self._progress_spin.value()
        task.activity_log.append({
            "ts": datetime.now().isoformat(),
            "content": entry_content,
            "status": task.status.value,
            "progress": task.progress,
        })
        task.updated_at = datetime.now()
        self._repository.update(task)
        self._original_md = task.raw_md
        if self._task_model:
            self._task_model.update_task(task)
        if task.status != old_status:
            self._signal_bus.task_status_changed.emit(task, old_status)
        else:
            self._signal_bus.task_updated.emit(task)
        self._log_edit.clear()
        self._refresh_timeline()

    # ------------------------------------------------------------------
    # Edit / delete existing entry
    # ------------------------------------------------------------------



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
        return ts.strftime("%m-%d %H:%M:%S")
    return ts.strftime("%Y-%m-%d %H:%M:%S")
