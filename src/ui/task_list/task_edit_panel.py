"""Inline task editor panel with card-style timeline, detail editing, and multi-select."""

from __future__ import annotations

import re

from datetime import date, datetime, timedelta
from typing import Callable

from PySide6.QtCore import QDate, QDateTime, QEvent, QPointF, QRect, QSize, QTime, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QBrush, QColor, QIntValidator, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

import sys
from pathlib import Path as _Path

from ...config import AppConfig
from ...models.repository import TaskRepository
from ...models.task import Task
from ...models.task_status import TaskStatus
from ...services.md_formatter import MarkdownTaskFormatter
from ...services.md_parser import MarkdownTaskParser
from ...utils.design_tokens import get_tokens
from ...utils.signal_bus import get_signal_bus
from ..widgets.deadline_calculator import DeadlineIntervalCalculator
from ...utils.widget_utils import combo_width
from ..widgets.dropdown import DropdownWidget


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
            "font-size: 11px; border: none; background: transparent;"
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

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            anchor = self.anchorAt(event.pos())
            if anchor.startswith("entry:"):
                return
        super().mouseReleaseEvent(event)

    def setSource(self, url) -> None:
        if url.scheme() == "entry":
            return
        super().setSource(url)


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

        # Background image (fill, crop excess to avoid letterboxing)
        if self._bg_pixmap:
            if self._scaled_bg is None:
                self._scaled_bg = self._bg_pixmap.scaled(
                    w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            p.drawPixmap(0, 0, self._scaled_bg)
        else:
            t = get_tokens()
            p.setBrush(QBrush(QColor(t.bg_welcome_fallback)))
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
        self._banner_active: bool = False

        self.setObjectName("taskEditPanel")
        self.setMinimumWidth(320)

        # Preload welcome background
        self._welcome_pixmap = QPixmap(_welcome_bg_path()) if _welcome_bg_path() else QPixmap()

        # Outer layout: section header (fixed) + scroll area
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Section header ("首页" or "编辑任务") — fixed, outside scroll area ---
        self._editor_header_widget = QWidget()
        header_row = QHBoxLayout(self._editor_header_widget)
        header_row.setContentsMargins(10, 6, 10, 6)
        self._section_label = QLabel("首页")
        self._section_label.setStyleSheet(
            "font-weight: bold; font-size: 11px;"
        )
        header_row.addWidget(self._section_label)
        header_row.addStretch()
        self._collapse_btn = QPushButton("▼")
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setStyleSheet("font-size: 10px; padding: 0;")
        self._collapse_btn.setToolTip("折叠编辑区")
        self._collapse_btn.clicked.connect(self._on_toggle_collapse)
        self._collapse_btn.setVisible(False)
        header_row.addWidget(self._collapse_btn)
        self._editor_header_widget.setVisible(True)
        outer.addWidget(self._editor_header_widget)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        self._scroll_content = QWidget()
        layout = QVBoxLayout(self._scroll_content)
        layout.setContentsMargins(10, 0, 10, 6)
        layout.setSpacing(6)

        # --- Draft banner ---
        self._draft_banner = _BannerWidget()
        self._draft_banner.setVisible(False)
        self._draft_banner.setMinimumHeight(120)
        layout.addWidget(self._draft_banner)

        # --- 编辑任务 section header (visible in welcome/empty state) ---
        self._editor_section_label = QLabel("编辑任务")
        self._editor_section_label.setStyleSheet(
            "font-weight: bold; font-size: 11px; padding: 6px 0;"
        )
        self._editor_section_label.setVisible(True)
        layout.addWidget(self._editor_section_label)

        # Collapsible editor content (20% when visible)
        self._editor_collapsible = QWidget()
        ec = QVBoxLayout(self._editor_collapsible)
        ec.setContentsMargins(0, 0, 0, 0)
        ec.setSpacing(2)

        # Markdown editor (hidden by default)
        self._md_editor_wrapper = QWidget()
        md_l = QVBoxLayout(self._md_editor_wrapper)
        md_l.setContentsMargins(0, 0, 0, 0)
        md_l.setSpacing(2)
        md_l.addWidget(QLabel("Markdown："))
        self._md_edit = QTextEdit()
        self._md_edit.setObjectName("mdEditor")
        self._md_edit.setPlaceholderText("- [ ]  <YYYY-MM-DD HH:MM> 标题 #标签")
        self._md_edit.setFixedHeight(48)  # compact 2-line default
        self._md_edit.textChanged.connect(self._on_text_changed)
        md_l.addWidget(self._md_edit)
        self._md_editor_wrapper.setVisible(False)
        ec.addWidget(self._md_editor_wrapper)

        self._preview_render = QLabel("(选择任务进行编辑)")
        self._preview_render.setTextFormat(Qt.TextFormat.RichText)
        self._preview_render.setWordWrap(True)
        self._preview_render.setObjectName("taskPreview")
        self._preview_render.setStyleSheet(
            "QLabel#taskPreview { padding: 4px 8px; border-radius: 4px; font-size: 12px; background: rgba(128,128,128,0.05); }"
        )
        self._preview_render.setMinimumHeight(36)
        ec.addWidget(self._preview_render)

        # Compact single row: time metadata + action buttons
        time_row = QHBoxLayout()
        time_row.setSpacing(6)
        self._created_label = QLabel("创建: —")
        self._created_label.setStyleSheet(
            f"font-size: 11px; color: {get_tokens().text_secondary};"
        )
        time_row.addWidget(self._created_label)
        dl_label = QLabel("截止:")
        dl_label.setStyleSheet("font-size: 11px;")
        time_row.addWidget(dl_label)
        self._deadline_date_edit = QDateEdit()
        self._deadline_date_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._deadline_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._deadline_date_edit.setDate(QDate.currentDate())
        self._deadline_date_edit.setMinimumDate(QDate(2000, 1, 1))
        self._deadline_date_edit.setMaximumDate(QDate(2100, 12, 31))
        self._deadline_date_edit.setFixedWidth(105)
        self._deadline_date_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._deadline_date_edit.setToolTip("点击选择日期")
        self._deadline_date_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._deadline_date_edit.dateChanged.connect(self._on_deadline_picker_changed)
        self._deadline_date_edit.lineEdit().installEventFilter(self)
        time_row.addWidget(self._deadline_date_edit)
        self._deadline_time_edit = QTimeEdit()
        self._deadline_time_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._deadline_time_edit.setDisplayFormat("HH:mm")
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._deadline_time_edit.setFixedWidth(60)
        self._deadline_time_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._deadline_time_edit.setToolTip("点击选择时间")
        self._deadline_time_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._deadline_time_edit.timeChanged.connect(self._on_deadline_picker_changed)
        self._deadline_time_edit.lineEdit().installEventFilter(self)
        time_row.addWidget(self._deadline_time_edit)
        self._quick_set_btn = QPushButton("快速计算")
        self._quick_set_btn.setFixedWidth(72)
        self._quick_set_btn.setStyleSheet("font-size: 10px; padding: 2px 4px;")
        self._quick_set_btn.clicked.connect(self._on_quick_set_deadline)
        time_row.addWidget(self._quick_set_btn)
        time_row.addStretch()
        self._edit_toggle_btn = QPushButton("编辑")
        self._edit_toggle_btn.setCheckable(True)
        self._edit_toggle_btn.setChecked(False)
        self._edit_toggle_btn.setFixedWidth(56)
        self._edit_toggle_btn.setStyleSheet("font-size: 10px; padding: 2px 4px;")
        self._edit_toggle_btn.clicked.connect(self._on_toggle_edit)
        time_row.addWidget(self._edit_toggle_btn)
        self._save_btn = QPushButton("保存")
        self._save_btn.setObjectName("saveBtn")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        self._save_btn.setFixedWidth(56)
        self._save_btn.setStyleSheet("font-size: 10px; padding: 2px 4px;")
        time_row.addWidget(self._save_btn)
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setObjectName("deleteBtn")
        self._delete_btn.clicked.connect(self._on_delete)
        self._delete_btn.setEnabled(False)
        self._delete_btn.setFixedWidth(56)
        self._delete_btn.setStyleSheet("font-size: 10px; padding: 2px 4px;")
        time_row.addWidget(self._delete_btn)
        ec.addLayout(time_row)
        # Editor card (bordered wrapper, collapse button in top-right corner)
        self._editor_card = QWidget()
        self._editor_card.setObjectName("editorCard")
        card_layout = QVBoxLayout(self._editor_card)
        card_layout.setContentsMargins(8, 8, 8, 6)
        card_layout.setSpacing(4)
        card_layout.addWidget(self._editor_collapsible)
        # Task summary (visible when collapsed)
        self._task_summary = QLabel()
        self._task_summary.setTextFormat(Qt.TextFormat.RichText)
        self._task_summary.setWordWrap(True)
        self._task_summary.setStyleSheet(
            "QLabel { font-size: 12px; padding: 4px 0; background: transparent; }"
        )
        self._task_summary.setVisible(False)
        card_layout.addWidget(self._task_summary)
        layout.addWidget(self._editor_card)

        # Separator between editor and timeline sections
        self._section_separator = QWidget()
        self._section_separator.setFixedHeight(1)
        self._section_separator.setStyleSheet("background: palette(mid);")
        self._section_separator.setVisible(False)
        layout.addWidget(self._section_separator)

        # Timeline section header
        self._timeline_header = QLabel("活动时间线")
        self._timeline_header.setStyleSheet("font-weight: bold; font-size: 11px; padding: 6px 0px;")
        self._timeline_header.setVisible(False)
        layout.addWidget(self._timeline_header)

        # ==================================================================
        # Timeline card
        # ==================================================================

        self._timeline_card = QWidget()
        self._timeline_card.setObjectName("timelineCard")
        tc = QVBoxLayout(self._timeline_card)
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(4)

        # -- Progress buttons ABOVE timeline (compact) --
        progress_btn_row = QHBoxLayout()
        progress_btn_row.setSpacing(4)
        self._status_combo = DropdownWidget()
        self._status_combo.setObjectName("timelineStatusCombo")
        self._status_combo.setFixedWidth(90)
        for s in (TaskStatus.DOING, TaskStatus.DONE):
            self._status_combo.addItem(f"● {s.display_name}", s)
            from PySide6.QtGui import QColor
            self._status_combo.setItemData(
                self._status_combo.count() - 1,
                QColor(s.display_color),
                Qt.ItemDataRole.ForegroundRole,
            )
        self._status_combo.setEnabled(False)
        progress_btn_row.addWidget(self._status_combo)
        self._progress_edit = QLineEdit()
        self._progress_edit.setValidator(QIntValidator(0, 100))
        self._progress_edit.setText("0")
        self._progress_edit.setFixedWidth(42)
        self._progress_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_edit.setEnabled(False)
        tk = get_tokens()
        self._progress_edit.setStyleSheet(
            f"QLineEdit {{ color: {tk.text_primary}; background: {tk.bg_secondary}; "
            f"border: 1px solid {tk.border_primary}; border-radius: 3px; }}"
            f"QLineEdit:disabled {{ color: {tk.text_secondary}; background: transparent; }}"
        )
        progress_btn_row.addWidget(self._progress_edit)
        progress_btn_row.addWidget(QLabel("%"))
        self._log_save_btn = QPushButton("追加进展")
        self._log_save_btn.setObjectName("saveBtn")
        self._log_save_btn.clicked.connect(self._on_log_save)
        self._log_save_btn.setEnabled(False)
        progress_btn_row.addWidget(self._log_save_btn)
        progress_btn_row.addStretch()
        tc.addLayout(progress_btn_row)

        # -- Timeline log (scrollable, 65% of card) --
        self._timeline_log = _TimelineBrowser()
        self._timeline_log.setReadOnly(True)
        self._timeline_log.setMinimumHeight(120)
        self._timeline_log.setStyleSheet(
            "QTextBrowser { font-size: 12px; padding: 4px; }"
        )
        self._entry_placeholder = QLabel("  (选择任务查看活动时间线)")
        self._entry_placeholder.setStyleSheet("font-size: 11px; padding: 8px;")
        self._entry_placeholder.setVisible(False)
        tc.addWidget(self._entry_placeholder)
        self._timeline_log.entry_clicked.connect(self._on_timeline_entry_clicked)
        tc.addWidget(self._timeline_log, 3)  # stretch 3 = 65%
        self._timeline_log.setVisible(False)

        # -- Progress input text (15% of card) --
        self._log_edit = QTextEdit()
        self._log_edit.setPlaceholderText("输入进展内容…")
        self._log_edit.setMinimumHeight(28)
        self._log_edit.setMaximumHeight(50)
        self._log_edit.setEnabled(False)
        self._log_edit.setStyleSheet(
            f"QTextEdit {{ font-size: 12px; color: {tk.text_primary}; "
            f"background: {tk.bg_secondary}; border: 1px solid {tk.border_primary}; "
            f"border-radius: 4px; padding: 4px; }}"
        )
        tc.addWidget(self._log_edit, 1)  # stretch 1 = 15%

        layout.addWidget(self._timeline_card, 4)
        self._timeline_card.setVisible(False)

        self._scroll_area.setWidget(self._scroll_content)
        outer.addWidget(self._scroll_area, 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_task(self, task: Task) -> None:
        self._current_task = task
        self._original_md = task.raw_md
        self._md_edit.blockSignals(True)
        self._md_edit.setText(task.raw_md)
        self._md_edit.blockSignals(False)

        self._banner_active = False
        self._draft_banner.setFixedHeight(120)
        self._draft_banner.setVisible(False)
        self._editor_section_label.setVisible(False)
        self._section_label.setText("编辑任务")
        self._editor_header_widget.setVisible(True)
        self._editor_card.setProperty("bordered", True)
        self._editor_card.style().unpolish(self._editor_card)
        self._editor_card.style().polish(self._editor_card)
        self._section_separator.setVisible(True)
        self._timeline_header.setVisible(True)
        self._collapse_btn.setVisible(True)
        self._editor_collapsible.setVisible(False)  # default collapsed
        self._collapse_btn.setText("▼")
        # Default: hide markdown editor, show preview only
        self._md_editor_wrapper.setVisible(False)
        self._edit_toggle_btn.setText("编辑")
        # Show task summary when collapsed
        self._task_summary.setText(f'任务：<b>{task.title}</b>')
        self._task_summary.setVisible(True)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(True)
        self._log_edit.setEnabled(True)
        self._log_save_btn.setEnabled(True)
        self._timeline_card.setVisible(True)

        # Status combo: OVERDUE shows only "逾期"; others show DOING/DONE
        self._status_combo.blockSignals(True)
        self._status_combo.clear()
        if task.status == TaskStatus.OVERDUE:
            self._status_combo.addItem(f"● {TaskStatus.OVERDUE.display_name}", TaskStatus.OVERDUE)
            self._status_combo.setEnabled(False)
        else:
            for s in (TaskStatus.DOING, TaskStatus.DONE):
                self._status_combo.addItem(f"● {s.display_name}", s)
            self._status_combo.setEnabled(True)
            target = task.status if task.status != TaskStatus.TODO else TaskStatus.DOING
            for i in range(self._status_combo.count()):
                if self._status_combo.itemData(i) == target:
                    self._status_combo.setCurrentIndex(i)
                    break
        self._status_combo.blockSignals(False)

        # Set date/time pickers
        self._updating_from_md = True
        if task.deadline_date:
            qd = QDate(task.deadline_date.year, task.deadline_date.month, task.deadline_date.day)
            self._deadline_date_edit.setDate(qd)
            if task.deadline_time:
                h, m = task.deadline_time.split(":")
                self._deadline_time_edit.setTime(QTime(int(h), int(m)))
            else:
                self._deadline_time_edit.setTime(QTime(23, 59))
        else:
            self._deadline_date_edit.setDate(QDate.currentDate())
            self._deadline_time_edit.setTime(QTime(23, 59))
        self._updating_from_md = False

        # Set created_at label (auto-generated, read-only)
        if task.created_at:
            self._created_label.setText(f"创建: {task.created_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            self._created_label.setText("创建: —")

        # Update preview labels
        self._progress_edit.setText(str(task.progress))
        self._progress_edit.setEnabled(True)
        self._update_preview()
        self._refresh_timeline()
        self._reset_log_editor()

    def clear(self) -> None:
        self._current_task = None
        self._original_md = ""
        self._md_edit.blockSignals(True)
        self._md_edit.clear()
        self._md_edit.blockSignals(False)
        self._section_label.setText("首页")
        self._editor_section_label.setVisible(True)
        self._editor_header_widget.setVisible(True)
        self._editor_card.setProperty("bordered", False)
        self._editor_card.style().unpolish(self._editor_card)
        self._editor_card.style().polish(self._editor_card)
        self._section_separator.setVisible(False)
        self._timeline_header.setVisible(False)
        self._collapse_btn.setVisible(False)
        self._editor_collapsible.setVisible(True)
        self._task_summary.setVisible(False)
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._status_combo.setEnabled(False)
        self._log_edit.setEnabled(False)
        self._log_save_btn.setEnabled(False)
        self._banner_active = False
        self._draft_banner.setFixedHeight(120)
        self._draft_banner.setVisible(False)
        self._preview_render.setText("(选择任务进行编辑)")
        self._timeline_card.setVisible(False)

        self._updating_from_md = True
        self._deadline_date_edit.setDate(QDate.currentDate())
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._created_label.setText("创建: —")
        self._created_label.setText("创建: —")
        # removed _preview_deadline("截止: —")
        self._updating_from_md = False
        self._clear_entries()
        self._hide_log_detail()
    
    def _build_welcome_html(self) -> str:
        t = get_tokens()
        c = t.text_welcome_accent
        s = t.text_welcome_sub
        return (
            f'<span style="font-size:12px;color:{c};letter-spacing:4px;">'
            '─ 宜 ─</span><br>'
            '<span style="font-size:28px;">🎉</span><br>'
            f'<span style="font-size:20px;color:{c};font-weight:bold;">'
            '今日无事</span><br>'
            f'<span style="font-size:13px;color:{s};letter-spacing:2px;">'
            '宜狂欢 · 忌加班</span><br>'
            f'<span style="font-size:12px;color:{c};letter-spacing:4px;">'
            '─ 忌 ─</span>'
        )

    def _build_draft_html(self) -> str:
        t = get_tokens()
        c = t.text_welcome_accent
        s = t.text_welcome_sub
        return (
            f'<span style="font-size:12px;color:{c};letter-spacing:4px;">'
            '─ 宜 ─</span><br>'
            '<span style="font-size:28px;">✍️</span><br>'
            f'<span style="font-size:20px;color:{c};font-weight:bold;">'
            '今日无事</span><br>'
            f'<span style="font-size:13px;color:{s};letter-spacing:2px;">'
            '宜创作 · 忌虚度</span><br>'
            f'<span style="font-size:12px;color:{c};letter-spacing:4px;">'
            '─ 忌 ─</span>'
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._banner_active:
            self._adjust_banner_height()

    def _adjust_banner_height(self) -> None:
        """Set banner to 60% of viewport height for welcome/draft states."""
        vh = self._scroll_area.viewport().height()
        if vh > 0:
            banner_h = max(120, int(vh * 0.6))
            self._draft_banner.setFixedHeight(banner_h)

    def show_empty(self) -> None:
        """Show welcome state — banner + directly editable Markdown template."""
        self._current_task = None
        self._original_md = ""
        self._banner_active = True
        self._draft_banner.set_html(self._build_welcome_html())
        self._draft_banner.set_bg_pixmap(self._welcome_pixmap)
        self._draft_banner.setVisible(True)
        self._adjust_banner_height()

        now_str = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm")
        template = f"- [ ]  <{now_str}> 新任务 #标签"
        self._md_edit.blockSignals(True)
        self._md_edit.setText(template)
        self._md_edit.blockSignals(False)
        self._update_preview()

        self._section_label.setText("首页")
        self._editor_section_label.setVisible(True)
        self._editor_header_widget.setVisible(True)
        self._editor_card.setProperty("bordered", False)
        self._editor_card.style().unpolish(self._editor_card)
        self._editor_card.style().polish(self._editor_card)
        self._section_separator.setVisible(False)
        self._timeline_header.setVisible(False)
        self._collapse_btn.setVisible(False)
        self._editor_collapsible.setVisible(True)
        self._task_summary.setVisible(False)

        # Direct edit mode — same experience as 新建任务
        self._md_editor_wrapper.setVisible(True)
        self._edit_toggle_btn.setText("关闭编辑")
        self._md_edit.setStyleSheet(
            "QTextEdit#mdEditor { border: 2px solid #5b8def; background: #f0f4ff; }"
        )
        QTimer.singleShot(800, lambda: self._md_edit.setStyleSheet(""))
        self._save_btn.setEnabled(True)
        self._delete_btn.setEnabled(False)

        self._status_combo.blockSignals(True)
        self._status_combo.clear()
        for s in (TaskStatus.DOING, TaskStatus.DONE):
            self._status_combo.addItem(f"● {s.display_name}", s)
        self._status_combo.setCurrentIndex(0)
        self._status_combo.setEnabled(True)
        self._status_combo.blockSignals(False)
        self._log_edit.setEnabled(True)
        self._log_save_btn.setEnabled(True)
        self._progress_edit.setText("0")
        self._progress_edit.setEnabled(True)
        self._created_label.setText(f"创建: {now_str}")
        self._timeline_card.setVisible(False)

        self._updating_from_md = True
        self._deadline_date_edit.setDate(QDate.currentDate())
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._updating_from_md = False
        self._clear_entries()
        self._hide_log_detail()

    def current_task(self) -> Task | None:
        return self._current_task

    def show_details(self, task: Task) -> None:
        self.load_task(task)

    def set_active_partition(self, partition_id: str | None) -> None:
        """Set the partition for the next draft task."""
        self._draft_partition_id = partition_id

    def create_draft(self, deadline_date: date | None = None) -> None:
        """Create an in-memory draft task with current time and mandatory tag template."""
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M")
        today = date.today()
        if deadline_date is not None:
            target = deadline_date
        else:
            # Default deadline: nearest Friday 23:59
            weekday = today.isoweekday()
            days_ahead = (5 - weekday) % 7
            if days_ahead == 0:
                days_ahead = 7
            target = today + timedelta(days=days_ahead)
        template = f"- [ ]  <{now_str}> 新任务 #待分类"
        parsed = self._parser.parse(template)
        from ...models.task import Task as TaskCls

        draft = TaskCls(
            id="",
            raw_md=template,
            title=parsed.clean_title,
            status=parsed.status,
            tags=parsed.tags,
            scheduled_date=parsed.scheduled_date,
            deadline_date=target,
            deadline_time="23:59",
            created_at=now,
            updated_at=now,
        )
        self._current_task = draft
        self._original_md = ""
        self._md_edit.blockSignals(True)
        self._md_edit.setText(template)
        self._md_edit.blockSignals(False)

        self._banner_active = True
        self._draft_banner.set_html(self._build_draft_html())
        self._draft_banner.set_bg_pixmap(self._welcome_pixmap)
        self._draft_banner.setVisible(True)
        self._adjust_banner_height()
        self._section_label.setText("首页")
        self._editor_section_label.setVisible(True)
        self._editor_header_widget.setVisible(True)
        self._editor_card.setProperty("bordered", False)
        self._editor_card.style().unpolish(self._editor_card)
        self._editor_card.style().polish(self._editor_card)
        self._section_separator.setVisible(False)
        self._timeline_header.setVisible(False)
        self._collapse_btn.setVisible(False)
        self._editor_collapsible.setVisible(True)
        self._task_summary.setVisible(False)
        # Auto-enter edit mode for draft
        self._md_editor_wrapper.setVisible(True)
        self._edit_toggle_btn.setText("关闭编辑")
        self._md_edit.setFocus()
        self._md_edit.selectAll()
        self._md_edit.setStyleSheet(
            "QTextEdit#mdEditor { border: 2px solid #5b8def; background: #f0f4ff; }"
        )
        QTimer.singleShot(800, lambda: self._md_edit.setStyleSheet(""))
        self._save_btn.setEnabled(True)
        self._delete_btn.setEnabled(False)
        self._status_combo.blockSignals(True)
        self._status_combo.clear()
        for s in (TaskStatus.DOING, TaskStatus.DONE):
            self._status_combo.addItem(f"● {s.display_name}", s)
        self._status_combo.setCurrentIndex(0)
        self._status_combo.setEnabled(True)
        self._status_combo.blockSignals(False)
        self._progress_edit.setText(str(0))
        self._progress_edit.setEnabled(True)
        self._timeline_card.setVisible(False)
        self._timeline_log.clear()
        # Set pickers
        self._updating_from_md = True
        self._created_label.setText(f"创建: {now.strftime('%Y-%m-%d %H:%M')}")
        self._deadline_date_edit.setDate(QDate(target.year, target.month, target.day))
        self._deadline_time_edit.setTime(QTime(23, 59))
        self._updating_from_md = False
        self._created_label.setText(f"创建: {now.strftime('%Y-%m-%d %H:%M')}")
        # removed _preview_deadline(f"截止: {target.isoformat()} 23:59")
        self._update_preview()
        self._clear_entries()

    def create_draft_multi(self) -> None:
        """Create a multi-task draft with pre-populated template lines."""
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M")
        template = (
            f"- [ ]  <{now_str}> 新任务1 #标签\n"
            f"- [ ]  <{now_str}> 新任务2 #标签\n"
            f"- [ ]  <{now_str}> 新任务3 #标签"
        )
        self.create_draft()
        self._md_edit.blockSignals(True)
        self._md_edit.setText(template)
        self._md_edit.blockSignals(False)
        self._md_editor_wrapper.setVisible(True)
        self._edit_toggle_btn.setText("关闭编辑")

    def has_unsaved_draft(self) -> bool:
        """Return True if the panel holds an in-memory draft (not yet in DB)."""
        return self._current_task is not None and self._current_task.id == ""

    def discard_draft(self) -> None:
        """Discard the current draft without saving to DB."""
        if self.has_unsaved_draft():
            self.clear()

    def refresh_theme(self) -> None:
        """Re-apply theme-dependent colours after a theme switch."""
        t = get_tokens()
        # Rebuild welcome/draft banner HTML with current tokens
        if self._draft_banner.isVisible():
            if self._current_task is not None and self._current_task.id == "":
                self._draft_banner.set_html(self._build_draft_html())
            elif self._current_task is None:
                self._draft_banner.set_html(self._build_welcome_html())
        # Refresh timeline display if a task is loaded
        if self._current_task is not None and self._current_task.id != "":
            self._refresh_timeline()

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
        # Auto-expand editor when content exceeds 2 lines
        self._auto_resize_editor()

    def _auto_resize_editor(self) -> None:
        """Expand editor height when content needs more than 2 lines."""
        doc_h = int(self._md_edit.document().size().height())
        if doc_h > 48:
            self._md_edit.setMinimumHeight(min(doc_h + 8, 200))
            self._md_edit.setMaximumHeight(200)

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
            if parsed.deadline_time:
                h, m = parsed.deadline_time.split(":")
                self._deadline_time_edit.setTime(QTime(int(h), int(m)))
            else:
                self._deadline_time_edit.setTime(QTime(23, 59))
        else:
            self._deadline_date_edit.blockSignals(True)
            self._deadline_date_edit.setDate(QDate.currentDate())
            self._deadline_date_edit.blockSignals(False)
            self._deadline_time_edit.setTime(QTime(23, 59))
        self._updating_from_md = False

    def _update_preview(self) -> None:
        text = self._md_edit.toPlainText().strip()
        if not text:
            self._preview_render.setText("(空)")
            self._created_label.setText("创建: —")
            # removed _preview_deadline("截止: —")
            return
        try:
            t = get_tokens()
            parsed = self._parser.parse(text)
            title = parsed.clean_title
            tags_str = " ".join(
                f"<span style='color:{t.accent};font-size:10px;'>{tag}</span>"
                for tag in (parsed.tags or [])
            )
            sc = parsed.status.display_color

            # Status badge
            html = (
                f"<span style='background:{sc};color:{t.text_on_accent};padding:1px 7px;"
                f"border-radius:3px;font-size:10px;'>{parsed.status.display_name}</span>"
            )

            if parsed.scheduled_date:
                html += (
                    f" <span style='color:{t.text_secondary};font-size:10px;'>"
                    f"📅{parsed.scheduled_date.isoformat()}</span>"
                )
            if parsed.deadline_date:
                html += (
                    f" <span style='color:{t.danger};font-size:10px;'>"
                    f"⏰{parsed.deadline_date.isoformat()}</span>"
                )
            html += f" <span style='font-size:12px;'>{title}</span>"
            if tags_str:
                html += f" {tags_str}"
            self._preview_render.setText(html)

            # Update time labels
        except ValueError:
            self._preview_render.setText(
                f'<span style="color:{get_tokens().danger};">⚠ 无法解析</span>'
            )
            self._created_label.setText("创建: —")
            # removed _preview_deadline("截止: —")

    # ------------------------------------------------------------------
    # Custom calendar popup
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(obj, event)
        if obj is self._deadline_date_edit.lineEdit():
            self._show_picker("date")
            return True
        if obj is self._deadline_time_edit.lineEdit():
            self._show_picker("time")
            return True
        return super().eventFilter(obj, event)

    def _show_picker(self, kind: str) -> None:
        if kind == "date":
            from ...ui.widgets.calendar_popup import CalendarPopup
            current = self._deadline_date_edit.date()
            task = self._current_task
            rf, rt, rk = None, None, ""
            if task is not None:
                if task.created_at:
                    rf = task.created_at.date()
                if task.deadline_date:
                    rt = task.deadline_date
                elif rf:
                    rt = rf
                if rf and rt:
                    if task.status == TaskStatus.DONE:
                        rk = "done"
                    elif task.deadline_date and rf <= date.today() and not task.archived:
                        rk = "overdue"
            popup = CalendarPopup(current, self, range_from=rf, range_to=rt, range_kind=rk)
            popup.date_selected.connect(self._on_calendar_date_selected)
            popup.smart_place(self._deadline_date_edit)
            popup.exec()
        else:
            from ...ui.widgets.time_popup import TimePopup
            current = self._deadline_time_edit.time()
            popup = TimePopup(current, self)
            popup.time_selected.connect(self._on_time_popup_selected)
            popup.smart_place(self._deadline_time_edit)
            popup.exec()

    def _on_calendar_date_selected(self, qdate: QDate) -> None:
        self._deadline_date_edit.setDate(qdate)

    def _on_time_popup_selected(self, t: QTime) -> None:
        self._deadline_time_edit.setTime(t)

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
        qt = self._deadline_time_edit.time()
        new_dl = f"<{new_date} {qt.toString('HH:mm')}>"
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
                kw_match = _re.search(r"(TODO|DOING|DONE|OVERDUE)\s*", text)
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
            self._reevaluate_overdue()
        self._updating_from_md = False


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
            # Ensure combo is populated (may be stale from previous task)
            self._status_combo.blockSignals(True)
            self._status_combo.clear()
            for s in (TaskStatus.DOING, TaskStatus.DONE):
                self._status_combo.addItem(f"● {s.display_name}", s)
            self._status_combo.setCurrentIndex(0)  # DOING
            self._status_combo.setEnabled(True)
            self._status_combo.blockSignals(False)
        text = self._md_edit.toPlainText().strip()
        if not text:
            return

        # Multi-task detection: any multi-line text creates N independent tasks
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) > 1:
            self._save_multi_tasks(lines)
            return

        try:
            parsed = self._parser.parse(text)
        except ValueError:
            QMessageBox.warning(self, "解析失败", "Markdown 格式不正确，请检查。")
            return

        # Tags are mandatory
        if not parsed.tags:
            QMessageBox.warning(
                self, "标签缺失",
                "标签是必填项，请至少添加一个 #标签（如 #工作、#个人、#学习）。"
            )
            return

        task = self._current_task
        old_status = task.status
        is_draft = task.id == ""
        combo_status = self._status_combo.currentData()
        task.title = parsed.clean_title
        # New drafts always start as TODO; combo only affects existing tasks
        task.status = parsed.status if is_draft else (combo_status if combo_status else parsed.status)
        task.tags = parsed.tags
        task.scheduled_date = parsed.scheduled_date
        task.deadline_date = parsed.deadline_date
        task.deadline_time = parsed.deadline_time
        # created_at is auto-generated — keep existing or set for new drafts
        if not task.created_at:
            task.created_at = datetime.now()
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

        # Validate: created_at must not be after deadline
        if task.created_at and task.deadline_date:
            cd = task.created_at.date()
            if cd > task.deadline_date:
                QMessageBox.warning(
                    self, "时间校验失败",
                    f"创建时间({cd.isoformat()})不能晚于截止时间({task.deadline_date.isoformat()})，请调整后再保存。"
                )
                return

        is_draft = task.id == ""
        if is_draft:
            import uuid
            task.id = str(uuid.uuid4())
            if self._draft_partition_id:
                task.partition_id = self._draft_partition_id
            now = datetime.now()
            task.activity_log.insert(0, {
                "ts": now.isoformat(),
                "content": "创建任务",
                "status": task.status.value,
                "progress": 0,
            })
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
        # Re-evaluate overdue status after save
        self._reevaluate_overdue()
        # Collapse editor after save
        self._collapse_btn.setVisible(True)
        self._editor_collapsible.setVisible(False)
        self._collapse_btn.setText("▼")
        self._task_summary.setText(f'任务：<b>{task.title}</b>')
        self._task_summary.setVisible(True)

    def _save_multi_tasks(self, lines: list[str]) -> None:
        """Split multi-line input into individual tasks and save them."""
        import uuid
        from ...models.task import Task as TaskCls

        # Discard draft immediately so signals don't interfere
        self._current_task = None
        self._original_md = ""
        self._save_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)

        now = datetime.now()
        dl_date = date(
            self._deadline_date_edit.date().year(),
            self._deadline_date_edit.date().month(),
            self._deadline_date_edit.date().day(),
        )
        dl_time = f"{self._deadline_time_edit.time().hour():02d}:{self._deadline_time_edit.time().minute():02d}"
        pid = self._draft_partition_id
        created = 0
        errors = []

        for i, line in enumerate(lines, 1):
            try:
                parsed = self._parser.parse(line)
            except ValueError:
                errors.append(f"第{i}行解析失败")
                continue
            if not parsed.tags:
                errors.append(f"第{i}行缺少标签")
                continue

            task_now = now + timedelta(seconds=i)
            task = TaskCls(
                id=str(uuid.uuid4()),
                raw_md=line,
                title=parsed.clean_title,
                status=parsed.status,
                tags=parsed.tags,
                scheduled_date=parsed.scheduled_date,
                deadline_date=parsed.deadline_date or dl_date,
                deadline_time=parsed.deadline_time or dl_time,
                partition_id=pid,
                created_at=task_now,
                updated_at=task_now,
                activity_log=[{
                    "ts": task_now.isoformat(),
                    "content": f"[批量创建] 创建任务 {i}/{len(lines)}",
                    "status": parsed.status.value,
                    "progress": 0,
                }],
            )
            # Apply formatter for canonical raw_md
            task.raw_md = self._formatter.format(task)
            self._repository.insert(task)
            created += 1

        if errors:
            QMessageBox.warning(
                self, "部分创建失败",
                "\n".join(errors) + f"\n\n成功创建 {created} 个任务。"
            )
        if created > 0:
            self._signal_bus.tasks_bulk_created.emit(created)
        self.clear()

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
    # Overdue re-evaluation
    # ------------------------------------------------------------------

    def _reevaluate_overdue(self) -> None:
        """Check if the current task should become OVERDUE or be reverted."""
        if not self._current_task:
            return
        task = self._current_task
        qdate = self._deadline_date_edit.date()
        dl_date = date(qdate.year(), qdate.month(), qdate.day())
        today = date.today()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        if task.status == TaskStatus.OVERDUE:
            # Was overdue — check if deadline moved to future
            if dl_date >= today and task.deadline_date is not None:
                old_dl = task.deadline_date.isoformat()
                new_dl = dl_date.isoformat()
                task.status = TaskStatus.DOING
                task.deadline_date = dl_date
                task.raw_md = self._formatter.format(task)
                task.updated_at = datetime.now()
                task.activity_log.append({
                    "ts": datetime.now().isoformat(),
                    "content": f"调整截至时间由{old_dl}->{new_dl}，状态由逾期->进行中",
                    "status": task.status.value,
                })
                self._repository.update(task)
                self._original_md = task.raw_md
                self._signal_bus.task_status_changed.emit(task, TaskStatus.OVERDUE)
                # Repopulate combo back to DOING/DONE
                self._status_combo.blockSignals(True)
                self._status_combo.clear()
                for s in (TaskStatus.DOING, TaskStatus.DONE):
                    self._status_combo.addItem(f"● {s.display_name}", s)
                self._status_combo.setEnabled(True)
                self._status_combo.setCurrentIndex(0)  # DOING
                self._status_combo.blockSignals(False)
                self._refresh_timeline()
        elif dl_date < today and task.status not in (TaskStatus.DONE, TaskStatus.OVERDUE):
            # Deadline passed and not DONE → OVERDUE
            old_status = task.status
            task.status = TaskStatus.OVERDUE
            task.deadline_date = dl_date
            task.raw_md = self._formatter.format(task)
            task.updated_at = datetime.now()
            task.activity_log.append({
                "ts": datetime.now().isoformat(),
                "content": f"超过截至时间({now_str}),当前项目已逾期",
                "status": task.status.value,
            })
            self._repository.update(task)
            self._original_md = task.raw_md
            self._signal_bus.task_status_changed.emit(task, old_status)
            # Populate combo with only OVERDUE (locked)
            self._status_combo.blockSignals(True)
            self._status_combo.clear()
            self._status_combo.addItem(f"● {TaskStatus.OVERDUE.display_name}", TaskStatus.OVERDUE)
            self._status_combo.setEnabled(False)
            self._status_combo.blockSignals(False)
            self._refresh_timeline()

    # ------------------------------------------------------------------
    # Collapse / expand editor
    # ------------------------------------------------------------------

    def _on_toggle_collapse(self) -> None:
        collapsed = self._editor_collapsible.isVisible()
        self._editor_collapsible.setVisible(not collapsed)
        self._collapse_btn.setText("▼" if collapsed else "▲")
        self._collapse_btn.setToolTip("展开编辑区" if collapsed else "折叠编辑区")
        self._task_summary.setVisible(collapsed)

    def _on_toggle_edit(self) -> None:
        showing = self._md_editor_wrapper.isVisible()
        self._md_editor_wrapper.setVisible(not showing)
        self._edit_toggle_btn.setText("关闭编辑" if not showing else "编辑")
        if not showing:
            self._section_label.setText("编辑任务")
            self._md_edit.setStyleSheet(
                "QTextEdit#mdEditor { border: 2px solid #5b8def; background: #f0f4ff; }"
            )
            self._md_edit.setFocus()
        else:
            self._section_label.setText("首页")
            self._md_edit.setStyleSheet("")

    def _on_quick_set_deadline(self) -> None:
        """Open deadline calculator popup."""
        from ..widgets.deadline_calculator import DeadlineIntervalCalculator
        dlg = DeadlineIntervalCalculator(parent=self)
        dlg.deadline_suggested.connect(self._on_deadline_suggested)
        dlg.exec()

    def _on_deadline_suggested(self, d: QDate, t: QTime) -> None:
        """Apply deadline suggestion from the calculator popup."""
        self._deadline_date_edit.blockSignals(True)
        self._deadline_date_edit.setDate(d)
        self._deadline_date_edit.blockSignals(False)
        self._deadline_time_edit.blockSignals(True)
        self._deadline_time_edit.setTime(t)
        self._deadline_time_edit.blockSignals(False)
        self._on_deadline_picker_changed()

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
        t = get_tokens()

        def _row(icon: str, color: str, ts: str, content: str, entry_idx: int | None = None) -> str:
            txt = t.text_primary
            if entry_idx is not None:
                return (
                    f'<p style="margin:3px 0;font-family:Consolas,monospace;font-size:12px;">'
                    f'<a href="entry:{entry_idx}" style="text-decoration:none;color:inherit;">'
                    f'<span style="color:{color};font-weight:bold;">{icon}</span>'
                    f' <span style="color:{color};">{ts:>11}</span>'
                    f' <span style="color:{txt};">{content}</span>'
                    f'</a>'
                    f'</p>'
                )
            return (
                f'<p style="margin:3px 0;font-family:Consolas,monospace;font-size:12px;">'
                f'<span style="color:{color};font-weight:bold;">{icon}</span>'
                f' <span style="color:{color};">{ts:>11}</span>'
                f' <span style="color:{txt};">{content}</span>'
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
                sc = t.text_secondary
                sn = st_val
            is_done = "任务完成" in content
            color = t.timeline_done if is_done else t.timeline_dot
            progress_val = e.get("progress", task.progress)
            rows.append(_row("●", color, ts,
                              f'<span style="color:{sc};">[{sn}|{progress_val}%]</span> {content}',
                              entry_idx=None if orig_idx == 0 else orig_idx))
        self._timeline_log.setHtml(f'<div>{"".join(rows)}</div>')
        self._reset_log_editor()

    def _on_timeline_entry_clicked(self, idx: int) -> None:
        """Populate the progress editor with the clicked timeline entry for editing."""
        if not self._current_task:
            return
        if idx < 0 or idx >= len(self._current_task.activity_log):
            return
        if idx == 0:
            return  # initial "创建任务" entry is locked

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
        self._progress_edit.setText(str(progress_val))

        self._log_save_btn.setText("更新进展")
        self._status_combo.setEnabled(False)  # status locked when editing



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
            self._progress_edit.setText(str(self._current_task.progress))
            if self._current_task.status != TaskStatus.OVERDUE:
                self._status_combo.setEnabled(True)

    # ------------------------------------------------------------------
    # Log editor actions
    # ------------------------------------------------------------------

    def _on_log_save(self) -> None:
        """Add or update progress: optionally change status + record text."""
        if not self._current_task:
            return
        content = self._log_edit.toPlainText().strip()
        raw_status = self._status_combo.currentData()
        task = self._current_task
        old_status = task.status

        # OVERDUE lock: cannot change status via progress
        if old_status == TaskStatus.OVERDUE:
            raw_status = TaskStatus.OVERDUE
        new_status = raw_status

        if self._selected_entry is not None:
            # ---- Editing an existing entry (content + progress only, status locked) ----
            idx, entry = self._selected_entry
            if not content:
                self._refresh_timeline()
                return
            entry["content"] = content
            entry["progress"] = int(self._progress_edit.text() or 0)
            task.progress = int(self._progress_edit.text() or 0)
            task.updated_at = datetime.now()
            self._repository.update(task)
            self._original_md = task.raw_md
            if self._task_model:
                self._task_model.update_task(task)
            self._signal_bus.task_updated.emit(task)
            self._log_edit.clear()
            self._refresh_timeline()
            return

        # ---- Appending a new entry ----
        if not content and new_status == old_status:
            QMessageBox.warning(
                self, "内容为空",
                "请输入进展备注内容后再提交。\n\n"
                "如果仅需更新进度，请在输入框中填入简要说明（如\"进度更新至XX%\"）。"
            )
            self._log_edit.setFocus()
            return
        if new_status and new_status != old_status:
            task.status = new_status
            if new_status == TaskStatus.DONE:
                task.completed_at = task.deadline_date or datetime.now()
            # Smart progress minimums (only when user hasn't explicitly set a value)
            cur_p = int(self._progress_edit.text() or 0)
            if new_status == TaskStatus.DONE:
                cur_p = 100
            elif old_status == TaskStatus.DONE and new_status == TaskStatus.DOING and cur_p == 0:
                cur_p = 80
            elif old_status == TaskStatus.TODO and cur_p == 0:
                cur_p = 30
            self._progress_edit.setText(str(cur_p))
            task.raw_md = self._formatter.format(task)
        # Record one entry with current status
        entry_content = content if content else f"状态变更为 {task.status.display_name}"
        task.progress = int(self._progress_edit.text() or 0)
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
    w.setObjectName("toolSeparator")
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
