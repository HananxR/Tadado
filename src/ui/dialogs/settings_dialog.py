"""Application settings dialog — single scrollable page."""

from __future__ import annotations

import logging
import re
from datetime import date

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...models.repository import TaskRepository
from ...utils.design_tokens import get_surface_color, get_tokens, is_dark
from ...utils.signal_bus import get_signal_bus
from ...utils.win32_theme import is_dark_mode_supported, set_window_dark_mode
from ..widgets.dropdown import DropdownWidget

_log = logging.getLogger("runlog")

_DROP_W = 120


class _CenterHost(QWidget):
    """Transparent host that centers a child widget via stretch-sandwich layout."""

    def __init__(self, child: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addStretch()
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch()
        h.addWidget(child)
        h.addStretch()
        v.addLayout(h)
        v.addStretch()


def _wrap_center(w: QWidget) -> QWidget:
    """Wrap a widget in a centered container for table cell alignment."""
    return _CenterHost(w)


def _section_header(text: str) -> QLabel:
    """Return a theme-coloured section header label."""
    t = get_tokens()
    label = QLabel(text)
    label.setStyleSheet(
        f"QLabel {{"
        f"  font-size: 13px; font-weight: bold;"
        f"  color: {t.text_primary};"
        f"  padding-top: 16px; padding-bottom: 4px;"
        f"}}"
    )
    return label


class SettingsDialog(QDialog):
    """Settings dialog — single scrollable page."""

    def __init__(
        self, config: AppConfig, repository: TaskRepository,
        task_service=None, parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._repository = repository
        self._task_service = task_service
        self._original_theme = config.theme

        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.resize(640, 560)
        self.setMinimumSize(520, 440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 12, 20, 12)

        t = get_tokens()

        def _label(text: str) -> QLabel:
            lb = QLabel(text)
            lb.setFixedWidth(100)
            lb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lb.setStyleSheet(f"QLabel {{ color: {t.text_primary}; font-size: 13px; }}")
            return lb

        def _field(*widgets: QWidget, spacing: int = 10) -> QWidget:
            w = QWidget()
            row = QHBoxLayout(w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(spacing)
            for widget in widgets:
                row.addWidget(widget)
            row.addStretch()
            return w

        grid = QGridLayout()
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(0, 100)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        r = 0

        def _row(label_text: str, *widgets: QWidget) -> None:
            nonlocal r
            grid.addWidget(_label(label_text), r, 0)
            grid.addWidget(_field(*widgets), r, 1)
            r += 1

        # ================================================================
        # 外观
        # ================================================================
        grid.addWidget(_section_header("外观"), r, 0, 1, 2); r += 1
        self._theme_combo = DropdownWidget()
        self._theme_combo.setFixedWidth(_DROP_W)
        self._theme_combo.addItem("浅色", "light")
        self._theme_combo.addItem("深色", "dark")
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == self._config.theme:
                self._theme_combo.setCurrentIndex(i)
                break
        self._minimize_cb = QCheckBox()
        self._minimize_cb.setChecked(self._config.minimize_to_tray)
        self._auto_start_cb = QCheckBox()
        self._auto_start_cb.setChecked(self._config.auto_start)
        _row("主题:", self._theme_combo)
        _row("最小化到托盘:", self._minimize_cb)
        _row("开机自动启动:", self._auto_start_cb)

        # ================================================================
        # 任务列表
        # ================================================================
        grid.addWidget(_section_header("任务列表"), r, 0, 1, 2); r += 1
        self._page_size_combo = DropdownWidget()
        self._page_size_combo.setFixedWidth(_DROP_W)
        for n in (20, 50, 100):
            self._page_size_combo.addItem(str(n), n)
        ps = self._config.get("general", "page_size", default=20)
        for i in range(self._page_size_combo.count()):
            if self._page_size_combo.itemData(i) == ps:
                self._page_size_combo.setCurrentIndex(i)
                break
        self._default_sort_combo = DropdownWidget()
        self._default_sort_combo.setFixedWidth(_DROP_W)
        for key, label in [("urgency", "优先级"), ("status", "状态"), ("deadline", "截止时间"),
                            ("created", "创建时间"), ("title", "标题")]:
            self._default_sort_combo.addItem(label, key)
        cur_sort = self._config.get("general", "default_sort", default="urgency")
        idx = self._default_sort_combo.findData(cur_sort)
        if idx >= 0:
            self._default_sort_combo.setCurrentIndex(idx)
        self._completed_last_cb = QCheckBox()
        self._completed_last_cb.setChecked(self._config.sort_completed_last)
        _row("每页条数:", self._page_size_combo)
        _row("默认排序:", self._default_sort_combo)
        _row("已完成置底:", self._completed_last_cb)

        # ================================================================
        # 活动热力图
        # ================================================================
        grid.addWidget(_section_header("活动热力图"), r, 0, 1, 2); r += 1
        self._heatmap_year_combo = DropdownWidget()
        self._heatmap_year_combo.setFixedWidth(_DROP_W)
        cur_year = date.today().year
        for y in range(cur_year - 5, cur_year + 1):
            self._heatmap_year_combo.addItem(str(y), y)
        saved_year = self._config.get("display", "heatmap_start_year", default=cur_year)
        idx = self._heatmap_year_combo.findData(saved_year)
        if idx < 0:
            self._heatmap_year_combo.insertItem(0, str(saved_year), saved_year)
            self._heatmap_year_combo.setCurrentIndex(0)
        else:
            self._heatmap_year_combo.setCurrentIndex(idx)
        self._color_scheme_combo = DropdownWidget()
        self._color_scheme_combo.setFixedWidth(_DROP_W)
        for key, label in [("sunbeam", "☀️ 暖阳"), ("sprout", "🌱 新绿"),
                           ("ocean", "🌊 海洋"), ("sakura", "🌸 樱花")]:
            self._color_scheme_combo.addItem(label, key)
        cur_scheme = self._config.get("display", "heatmap_color_scheme", default="sunbeam")
        idx = self._color_scheme_combo.findData(cur_scheme)
        if idx >= 0:
            self._color_scheme_combo.setCurrentIndex(idx)
        _row("起始年份:", self._heatmap_year_combo)
        _row("配色方案:", self._color_scheme_combo)

        # ================================================================
        # 归档 / 分区管理
        # ================================================================
        grid.addWidget(_section_header("归档 / 分区管理"), r, 0, 1, 2); r += 1

        btn_style = (
            f"QPushButton {{"
            f"  font-size: 11px; padding: 2px 10px; min-height: 22px;"
            f"  color: {t.accent}; border: 1px solid {t.border_primary};"
            f"  border-radius: 4px; background: transparent;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {t.bg_tertiary}; border-color: {t.accent};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  color: {t.text_disabled}; border-color: {t.border_primary};"
            f"}}"
        )
        toolbar = QWidget()
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(0, 0, 0, 2)
        tl.setSpacing(6)
        self._add_partition_btn = QPushButton("+ 新增")
        self._add_partition_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_partition_btn.setStyleSheet(btn_style)
        self._add_partition_btn.clicked.connect(self._on_add_partition_row)
        tl.addWidget(self._add_partition_btn)
        self._delete_partition_btn = QPushButton("− 删除")
        self._delete_partition_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_partition_btn.setStyleSheet(btn_style)
        self._delete_partition_btn.clicked.connect(self._on_delete_partition_rows)
        self._delete_partition_btn.setEnabled(False)
        tl.addWidget(self._delete_partition_btn)
        self._selection_label = QLabel("")
        self._selection_label.setStyleSheet(
            f"QLabel {{ color: {t.text_secondary}; font-size: 11px; }}"
        )
        tl.addWidget(self._selection_label)
        tl.addStretch()
        grid.addWidget(toolbar, r, 0, 1, 2); r += 1


        self._partition_table = QTableWidget(0, 5)
        self._partition_table.setHorizontalHeaderLabels(
            ["名称", "默认分区", "归档阈值(天)", "自动锁定(分)", "密码"]
        )
        hh = self._partition_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.resizeSection(1, 80)
        hh.resizeSection(2, 100)
        hh.resizeSection(3, 100)
        hh.resizeSection(4, 60)
        for c in (1, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        self._partition_table.verticalHeader().hide()
        self._partition_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._partition_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._partition_table.setAlternatingRowColors(True)
        self._partition_table.setShowGrid(True)
        self._partition_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._partition_table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._partition_table.itemSelectionChanged.connect(self._on_selection_changed)
        self._partition_table.setObjectName("settingsPartitionTable")
        table_qss = (
            f"QTableWidget#settingsPartitionTable {{"
            f"  border: 1px solid {t.border_primary};"
            f"  border-radius: 4px;"
            f"  gridline-color: {t.border_primary};"
            f"  selection-background-color: {t.bg_tertiary};"
            f"  selection-color: {t.text_primary};"
            f"  outline: none;"
            f"}}"
            f"QTableWidget#settingsPartitionTable QHeaderView::section {{"
            f"  text-align: center;"
            f"  background-color: {t.bg_secondary};"
            f"  color: {t.text_primary};"
            f"  font-weight: bold;"
            f"  font-size: 11px;"
            f"  padding: 6px 4px;"
            f"  border: none;"
            f"  border-bottom: 1px solid {t.border_primary};"
            f"  border-right: 1px solid {t.border_primary};"
            f"}}"
        )
        self._partition_table.setStyleSheet(table_qss)
        grid.addWidget(self._partition_table, r, 0, 1, 2); r += 1

        # ================================================================
        # AI 助手
        # ================================================================
        grid.addWidget(_section_header("AI 助手"), r, 0, 1, 2); r += 1
        self._ai_provider_combo = DropdownWidget()
        self._ai_provider_combo.setFixedWidth(_DROP_W)
        self._ai_provider_combo.addItem("自动检测（优先 Claude）", "")
        self._ai_provider_combo.addItem("Claude", "claude")
        self._ai_provider_combo.addItem("Codex", "codex")
        cur_provider = self._config.get("ai_assistant", "provider") or ""
        idx = self._ai_provider_combo.findData(cur_provider)
        self._ai_provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._ai_provider_combo.currentIndexChanged.connect(self._save_ai_assistant)
        _row("AI 助手:", self._ai_provider_combo)
        # 选择后即时校验可用性，不等托盘菜单才暴露不可用
        self._ai_status_label = QLabel("")
        self._ai_status_label.setWordWrap(True)
        self._ai_status_label.setStyleSheet(f"QLabel {{ font-size: 11px; }}")
        self._ai_provider_combo.currentIndexChanged.connect(self._refresh_ai_status)
        grid.addWidget(self._ai_status_label, r, 0, 1, 2); r += 1
        self._refresh_ai_status()

        content_layout.addLayout(grid)
        content_layout.addStretch()
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)

        # --- OK / Cancel buttons ---
        self._button_box = QDialogButtonBox()
        self._button_box.addButton("确认", QDialogButtonBox.ButtonRole.AcceptRole)
        self._button_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self._on_reject)
        self._button_box.setCenterButtons(True)
        outer.addWidget(self._button_box)

        # --- In-memory signal connections (persisted on OK) ---
        self._theme_combo.currentIndexChanged.connect(self._save_appearance)
        self._minimize_cb.toggled.connect(self._save_appearance)
        self._auto_start_cb.toggled.connect(self._save_appearance)
        self._page_size_combo.currentIndexChanged.connect(self._save_tasklist)
        self._default_sort_combo.currentIndexChanged.connect(self._save_tasklist)
        self._completed_last_cb.toggled.connect(self._save_tasklist)
        self._heatmap_year_combo.currentIndexChanged.connect(self._save_display)
        self._color_scheme_combo.currentIndexChanged.connect(self._save_display)
        self._populated = False

    # ------------------------------------------------------------------
    # QLabel ↔ QLineEdit swap helpers
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Double-click a table QLabel → swap to QLineEdit for editing."""
        if isinstance(obj, QLabel) and obj.property("table_edit") is True:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._swap_to_editor(obj)
                return True
        return super().eventFilter(obj, event)

    def _make_table_label(self, text: str, col: int, pid: str = "") -> QLabel:
        """Create a display-only QLabel (double-click to edit)."""
        lb = QLabel(text)
        lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb.setProperty("table_edit", True)
        lb.setProperty("edit_col", col)
        lb.setProperty("partition_id", pid)
        lb.installEventFilter(self)
        return lb

    def _commit_pending_edits(self) -> None:
        """Force any active QLineEdit back to QLabel before switching rows."""
        if getattr(self, "_committing", False):
            return
        self._committing = True
        try:
            for col in (0, 4, 5):
                for r in range(self._partition_table.rowCount()):
                    w = self._partition_table.cellWidget(r, col)
                    if isinstance(w, QLineEdit) and w.property("edit_col") is not None:
                        if w.property("pending_new") is True:
                            continue  # skip brand-new row, user hasn't typed yet
                        if col == 0:
                            self._on_name_edit_finished(w)
                        else:
                            self._swap_to_label(w)
        finally:
            self._committing = False

    def _swap_to_editor(self, label: QLabel) -> None:
        """Replace a QLabel with QLineEdit in the table."""
        self._commit_pending_edits()
        col = label.property("edit_col")
        pid = label.property("partition_id") or ""
        row = self._find_widget_row(col, label)
        if row < 0:
            return
        edit = QLineEdit(label.text())
        edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setFrame(True)
        edit.setFixedHeight(30)
        edit.setProperty("edit_col", col)
        edit.setProperty("partition_id", pid)
        if col == 0:
            edit.editingFinished.connect(lambda: self._on_name_edit_finished(edit))
        elif col in (4, 5):
            edit.editingFinished.connect(lambda: self._swap_to_label(edit))
        self._partition_table.setCellWidget(row, col, edit)
        edit.selectAll()
        edit.setFocus()

    def _swap_to_label(self, edit: QLineEdit) -> None:
        """Replace a QLineEdit back with QLabel."""
        col = edit.property("edit_col")
        pid = edit.property("partition_id") or ""
        row = self._find_widget_row(col, edit)
        if row < 0:
            return
        lb = self._make_table_label(edit.text(), col, pid)
        self._partition_table.setCellWidget(row, col, lb)

    def _find_widget_row(self, col: int, target: QWidget) -> int:
        """Find the table row containing *target* in column *col*."""
        for r in range(self._partition_table.rowCount()):
            if self._partition_table.cellWidget(r, col) is target:
                return r
        return -1

    def _on_name_edit_finished(self, edit: QLineEdit) -> None:
        """Auto-save name edit, then swap back to QLabel."""
        edit.setProperty("pending_new", False)
        new_name = edit.text().strip()
        pid = edit.property("partition_id") or ""

        if not new_name and pid:
            for p in self._partitions_data:
                if p["id"] == pid:
                    edit.setText(p["name"])
                    break
        if not new_name and not pid:
            row = self._find_widget_row(0, edit)
            if row >= 0:
                self._partition_table.removeRow(row)
                self._update_table_height()
            return

        # Duplicate name check
        if new_name and any(
            p["name"] == new_name and p["id"] != pid
            for p in self._partitions_data
        ):
            QMessageBox.warning(self, "名称重复", f'分区 "{new_name}" 已存在，请使用其他名称。')
            edit.setText("" if not pid else next(
                (p["name"] for p in self._partitions_data if p["id"] == pid), ""
            ))
            self._swap_to_label(edit)
            return

        if pid and new_name:
            self._repository.upsert_partition(new_name, partition_id=pid)
            _log.info("Partition renamed: id=%s new_name=%s", pid, new_name)
        elif not pid and new_name:
            result = self._repository.upsert_partition(new_name)
            _log.info("Partition created: %s id=%s", new_name, result["id"])
            edit.setProperty("partition_id", result["id"])
            row = self._find_widget_row(0, edit)
            if row >= 0:
                def_w = self._partition_table.cellWidget(row, 1)
                if def_w:
                    def_cb = def_w.findChild(QCheckBox)
                    if def_cb:
                        def_cb.toggled.connect(
                            lambda checked, r=row: self._on_default_toggled(r, checked)
                        )
            self._partitions_data.append(result)
            get_signal_bus().partitions_changed.emit()

        self._swap_to_label(edit)

    # ------------------------------------------------------------------
    # Partition table
    # ------------------------------------------------------------------

    def _populate_partition_table(self) -> None:
        self._partition_table.blockSignals(True)
        self._partitions_data = self._task_service.get_all_partitions() if self._task_service else self._repository.get_all_partitions()
        default_id = self._config.get("general", "default_partition", default="")

        self._partition_table.setRowCount(0)

        for p in self._partitions_data:
            row = self._partition_table.rowCount()
            self._partition_table.insertRow(row)
            self._partition_table.setRowHeight(row, 40)
            pid = p["id"]

            # 0: 名称 — QLabel (double-click to edit)
            self._partition_table.setCellWidget(
                row, 0, self._make_table_label(p["name"], 0, pid)
            )

            # 1: 默认分区 — QCheckBox
            def_cb = QCheckBox()
            def_cb.setStyleSheet("spacing: 0px;")
            def_cb.setChecked(pid == default_id)
            def_cb.toggled.connect(lambda checked, r=row: self._on_default_toggled(r, checked))
            self._partition_table.setCellWidget(row, 1, _wrap_center(def_cb))

            # 2: 归档阈值(天) — QLabel (double-click to edit)
            #     0=即时归档, 1-9998=N天后午夜归档, 9999=永不归档
            self._partition_table.setCellWidget(
                row, 2, self._make_table_label(str(p.get("archive_days", 0)), 2, pid)
            )

            # 3: 自动锁定(分) — QLabel (double-click to edit)
            self._partition_table.setCellWidget(
                row, 3, self._make_table_label(str(p.get("auto_lock_minutes", 3)), 3, pid)
            )

            # 4: 密码 — button
            tokens = get_tokens()
            has_pwd = bool(p.get("password", ""))
            pwd_btn = QPushButton("🔒" if has_pwd else "🔓")
            pwd_btn.setFlat(True)
            pwd_btn.setFixedSize(32, 32)
            pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            color = tokens.accent if has_pwd else tokens.text_secondary
            pwd_btn.setStyleSheet(
                f"QPushButton {{ font-size: 16px; color: {color}; border: none; background: transparent; padding: 0px; }}"
            )
            pwd_btn.clicked.connect(
                lambda checked=False, pid=pid: self._on_set_partition_password(pid)
            )
            self._partition_table.setCellWidget(row, 4, _wrap_center(pwd_btn))

        self._partition_table.verticalHeader().setDefaultSectionSize(40)
        self._update_table_height()

        if self._partition_table.rowCount() > 0:
            any_checked = False
            for r in range(self._partition_table.rowCount()):
                cw = self._partition_table.cellWidget(r, 1)
                if cw:
                    cb = cw.findChild(QCheckBox)
                    if cb and cb.isChecked():
                        any_checked = True
                        break
            if not any_checked:
                first_cw = self._partition_table.cellWidget(0, 1)
                if first_cw:
                    first_cb = first_cw.findChild(QCheckBox)
                    if first_cb:
                        first_cb.setChecked(True)
                        first_pid = self._partitions_data[0]["id"]
                        self._config.set("general", "default_partition", value=first_pid)

        self._partition_table.blockSignals(False)

    def _on_default_toggled(self, row: int, checked: bool) -> None:
        """Mutually exclusive default partition."""
        if not checked:
            other_checked = False
            for r in range(self._partition_table.rowCount()):
                if r == row:
                    continue
                cw = self._partition_table.cellWidget(r, 1)
                if cw:
                    cb = cw.findChild(QCheckBox)
                    if cb and cb.isChecked():
                        other_checked = True
                        break
            if not other_checked:
                cw = self._partition_table.cellWidget(row, 1)
                if cw:
                    cb = cw.findChild(QCheckBox)
                    if cb:
                        cb.blockSignals(True)
                        cb.setChecked(True)
                        cb.blockSignals(False)
                return
        else:
            for r in range(self._partition_table.rowCount()):
                cw = self._partition_table.cellWidget(r, 1)
                if cw and r != row:
                    cb = cw.findChild(QCheckBox)
                    if cb:
                        cb.blockSignals(True)
                        cb.setChecked(False)
                        cb.blockSignals(False)
        pid = self._partitions_data[row]["id"]
        self._config.set("general", "default_partition", value=pid)

    # ------------------------------------------------------------------
    # Selection tracking
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        self._commit_pending_edits()
        sel = self._partition_table.selectionModel().selectedRows()
        count = len(sel)
        self._delete_partition_btn.setEnabled(count > 0)
        if count > 0:
            self._selection_label.setText(f"已选 {count} 个分区")
        else:
            self._selection_label.setText("")

    # ------------------------------------------------------------------
    # Inline add / delete
    # ------------------------------------------------------------------

    def _on_add_partition_row(self) -> None:
        """Insert an empty row — name column directly editable."""
        self._commit_pending_edits()
        for r in range(self._partition_table.rowCount()):
            w = self._partition_table.cellWidget(r, 0)
            if isinstance(w, QLineEdit) and not w.property("partition_id") and not w.text().strip():
                w.setFocus()
                return

        row = self._partition_table.rowCount()
        self._partition_table.insertRow(row)
        self._partition_table.setRowHeight(row, 40)

        # Column 0: QLineEdit directly (new row, ready to type)
        name_edit = QLineEdit()
        name_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_edit.setFrame(True)
        name_edit.setFixedHeight(30)
        name_edit.setProperty("edit_col", 0)
        name_edit.setProperty("partition_id", "")
        name_edit.setProperty("pending_new", True)
        name_edit.editingFinished.connect(lambda: self._on_name_edit_finished(name_edit))
        self._partition_table.setCellWidget(row, 0, name_edit)

        # Column 1-3: checkboxes
        for col in (1, 2, 3):
            cb = QCheckBox()
            cb.setStyleSheet("spacing: 0px;")
            self._partition_table.setCellWidget(row, col, _wrap_center(cb))

        # Column 4-5: QLabel (double-click to edit)
        for col, default_text in [(4, "9999"), (5, "3")]:
            self._partition_table.setCellWidget(
                row, col, self._make_table_label(default_text, col)
            )

        # Column 6: password button
        tokens = get_tokens()
        pwd_btn = QPushButton("🔓")
        pwd_btn.setFlat(True)
        pwd_btn.setFixedSize(32, 32)
        pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pwd_btn.setStyleSheet(
            f"QPushButton {{ font-size: 16px; color: {tokens.text_secondary}; border: none; background: transparent; padding: 0px; }}"
        )
        self._partition_table.setCellWidget(row, 6, _wrap_center(pwd_btn))

        self._partition_table.verticalHeader().setDefaultSectionSize(40)
        self._update_table_height()
        name_edit.setFocus()

    def _update_table_height(self) -> None:
        MAX_TABLE_HEIGHT = 300
        n = max(1, self._partition_table.rowCount())
        h = self._partition_table.horizontalHeader().height() + n * 40 + 6
        desired = min(h, MAX_TABLE_HEIGHT)
        self._partition_table.setMinimumHeight(desired)
        self._partition_table.setMaximumHeight(MAX_TABLE_HEIGHT)

    def _on_delete_partition_rows(self) -> None:
        """Delete selected partition rows with validations."""
        self._commit_pending_edits()
        sel = self._partition_table.selectionModel().selectedRows()
        if not sel:
            return

        def _name_text(row: int) -> str:
            w = self._partition_table.cellWidget(row, 0)
            if isinstance(w, QLineEdit):
                return w.text().strip()
            if isinstance(w, QLabel):
                return w.text().strip()
            return ""

        def _pid(row: int) -> str:
            w = self._partition_table.cellWidget(row, 0)
            if w:
                return w.property("partition_id") or ""
            return ""

        pids_to_delete: list[str] = []
        names: list[str] = []
        for idx in sorted(sel, key=lambda i: i.row(), reverse=True):
            row = idx.row()
            pid = _pid(row)
            if not pid:
                self._partition_table.removeRow(row)
                continue
            pids_to_delete.append(pid)
            names.append(_name_text(row))

        if not pids_to_delete:
            self._update_table_height()
            get_signal_bus().partitions_changed.emit()
            return

        remaining = sum(1 for r in range(self._partition_table.rowCount()) if _pid(r))
        if remaining - len(pids_to_delete) < 1:
            QMessageBox.warning(self, "无法删除", "至少需要保留一个分区。")
            return

        for pid, name in zip(pids_to_delete, names):
            count = self._repository.count_tasks_in_partition(pid)
            if count > 0:
                QMessageBox.warning(
                    self, "无法删除",
                    f'分区 "{name}" 中还有 {count} 个任务，'
                    f"请先在任务管理中调整分区或者删除",
                )
                return

        name_list = "、".join(names)
        result = QMessageBox.question(
            self, "确认删除",
            f"确定要删除以下分区吗？\n{name_list}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        default_id = self._config.get("general", "default_partition", default="")
        for pid in pids_to_delete:
            if pid == default_id:
                for r in range(self._partition_table.rowCount()):
                    other_pid = _pid(r)
                    if other_pid and other_pid not in pids_to_delete:
                        self._config.set("general", "default_partition", value=other_pid)
                        break
            self._repository.delete_partition(pid)
            _log.info("Partition deleted via settings: id=%s", pid)

        self._populate_partition_table()
        get_signal_bus().partitions_changed.emit()

    def _on_table_context_menu(self, pos) -> None:
        idx = self._partition_table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        w = self._partition_table.cellWidget(row, 0)
        if w is None:
            return
        pid = w.property("partition_id") or ""
        if not pid:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_password = menu.addAction("设置密码")
        menu.addSeparator()
        act_delete = menu.addAction("删除")
        action = menu.exec(self._partition_table.viewport().mapToGlobal(pos))
        if action == act_password:
            self._on_set_partition_password(pid)
        elif action == act_delete:
            self._partition_table.selectRow(row)
            self._on_delete_partition_rows()

    def _on_set_partition_password(self, pid: str) -> None:
        has_pwd, cur = self._repository.check_partition_password(pid)
        if has_pwd:
            old, ok = QInputDialog.getText(
                self, "修改密码", "输入旧密码（留空清除，忘记请点OK后重置）：",
                QLineEdit.EchoMode.Password,
            )
            if not ok:
                return
            if not old:
                self._repository.set_partition_password(pid, "")
            elif old != cur:
                result = QMessageBox.question(
                    self, "密码错误",
                    "旧密码不正确。是否直接设置新密码？（无需旧密码）",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if result != QMessageBox.StandardButton.Yes:
                    return
                new, ok2 = QInputDialog.getText(
                    self, "重置密码", "输入新密码（留空则清除）：",
                    QLineEdit.EchoMode.Password,
                )
                if ok2:
                    self._repository.set_partition_password(pid, new)
            else:
                new, ok2 = QInputDialog.getText(
                    self, "设置新密码", "输入新密码（留空则清除）：",
                    QLineEdit.EchoMode.Password,
                )
                if ok2:
                    self._repository.set_partition_password(pid, new)
        else:
            pwd, ok = QInputDialog.getText(
                self, "设置密码", "输入密码（留空则取消）：",
                QLineEdit.EchoMode.Password,
            )
            if ok and pwd:
                self._repository.set_partition_password(pid, pwd)
        self._populate_partition_table()
        get_signal_bus().partitions_changed.emit()

    def showEvent(self, event) -> None:
        """Apply dark title bar + lazy-load partition table on first show."""
        super().showEvent(event)
        if not self._populated:
            self._populate_partition_table()
            self._populated = True
        if is_dark_mode_supported() and is_dark():
            set_window_dark_mode(self, True, caption_color=get_surface_color())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_time(text: str) -> bool:
        return bool(re.match(r"^\d{1,2}:\d{2}$", text))

    # ------------------------------------------------------------------
    # Accept / Reject
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        """Persist all in-memory changes and close."""
        from ...utils.win32_autostart import set_autostart
        set_autostart(self._auto_start_cb.isChecked())
        self._save_config()
        self.accept()

    def _on_reject(self) -> None:
        """Revert in-memory changes by reloading from disk."""
        self._config._load()
        self.reject()

    # ------------------------------------------------------------------
    # In-memory change helpers (persisted on OK, reverted on Cancel)
    # ------------------------------------------------------------------

    def _save_config(self) -> None:
        """Persist all pending in-memory changes to disk."""
        self._config.save()

    def _save_appearance(self) -> None:
        self._config.set("display", "theme", value=self._theme_combo.currentData())
        self._config.set("general", "minimize_to_tray", value=self._minimize_cb.isChecked())
        self._config.set("general", "auto_start", value=self._auto_start_cb.isChecked())

    def _save_tasklist(self) -> None:
        self._config.set("general", "page_size", value=self._page_size_combo.currentData())
        self._config.set("general", "default_sort", value=self._default_sort_combo.currentData())
        self._config.set("general", "sort_completed_last", value=self._completed_last_cb.isChecked())

    def _save_reminders(self) -> None:
        self._config.set("reminders", "enabled", value=self._reminders_cb.isChecked())
        dt = self._digest_time_edit.text().strip()
        if self._validate_time(dt):
            self._config.set("reminders", "daily_digest_time", value=dt)
        qs = self._quiet_start_edit.text().strip()
        qe = self._quiet_end_edit.text().strip()
        if self._validate_time(qs):
            self._config.set("reminders", "quiet_hours_start", value=qs)
        if self._validate_time(qe):
            self._config.set("reminders", "quiet_hours_end", value=qe)

    def _save_ai_assistant(self) -> None:
        self._config.set(
            "ai_assistant", "provider", value=self._ai_provider_combo.currentData()
        )

    def _refresh_ai_status(self) -> None:
        """选择变更后即时校验所选 AI 助手的可用性."""
        from ...services.ai_assistant import _resolve_cmd

        t = get_tokens()
        provider = self._ai_provider_combo.currentData()
        if provider:
            cmd = self._config.get("ai_assistant", f"{provider}_cmd") or provider
            path = _resolve_cmd(cmd)
            if path:
                self._ai_status_label.setStyleSheet(
                    f"QLabel {{ font-size: 11px; color: {t.success}; }}"
                )
                self._ai_status_label.setText(f"✓ 已检测到 {provider.capitalize()}：{path}")
            else:
                self._ai_status_label.setStyleSheet(
                    f"QLabel {{ font-size: 11px; color: {t.danger}; }}"
                )
                self._ai_status_label.setText(
                    f"✗ 未检测到 {provider.capitalize()}，AI 助手将不可用。"
                    f"请先安装或调整命令（config: ai_assistant.{provider}_cmd）"
                )
        else:  # 自动检测
            from ...services.ai_assistant import _resolve_cmd as _rc
            from ...services.ai_assistant import detect_provider

            detected = detect_provider(self._config)
            if detected:
                path = _rc(self._config.get("ai_assistant", f"{detected}_cmd") or detected)
                self._ai_status_label.setStyleSheet(
                    f"QLabel {{ font-size: 11px; color: {t.success}; }}"
                )
                self._ai_status_label.setText(
                    f"✓ 自动检测到 {detected.capitalize()}：{path}"
                )
            else:
                self._ai_status_label.setStyleSheet(
                    f"QLabel {{ font-size: 11px; color: {t.danger}; }}"
                )
                self._ai_status_label.setText(
                    "✗ 未检测到 Claude Code 或 Codex，AI 助手不可用"
                )

    def _save_display(self) -> None:
        self._config.set("display", "heatmap_start_year", value=self._heatmap_year_combo.currentData())
        self._config.set("display", "heatmap_color_scheme", value=self._color_scheme_combo.currentData())

    def _save_motd(self) -> None:
        motd_cfg = {}
        for key, edit in self._motd_edits.items():
            if edit.text().strip():
                motd_cfg[key] = edit.text().strip()
        self._config.set("motd", value=motd_cfg)

    def theme_changed(self) -> bool:
        return self._theme_combo.currentData() != "system"
