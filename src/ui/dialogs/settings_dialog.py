"""Application settings dialog — single scrollable page."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...models.repository import TaskRepository
from ...utils.design_tokens import get_surface_color, get_tokens, is_dark
from ...utils.win32_theme import set_window_dark_mode, is_dark_mode_supported
from ...utils.signal_bus import get_signal_bus
from ..widgets.dropdown import DropdownWidget

_DROP_W = 120


def _wrap_center(w: QWidget) -> QWidget:
    """Wrap a widget in a centered container for table cell alignment."""
    c = QWidget()
    lay = QHBoxLayout(c)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(w)
    lay.setContentsMargins(0, 0, 0, 0)
    return c


def _hrow(*widgets: QWidget, spacing: int = 6) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, QHBoxLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    lay.addStretch()
    return lay


class SettingsDialog(QDialog):
    """Settings dialog — single scrollable page."""

    def __init__(
        self, config: AppConfig, repository: TaskRepository, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._repository = repository
        self._original_theme = config.theme

        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.resize(600, 550)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        layout = outer  # all subsequent code uses `layout`

        # ── 外观 ──
        layout.addWidget(QLabel("<b>外观</b>"))
        self._theme_combo = DropdownWidget()
        self._theme_combo.setObjectName("settingsThemeCombo")
        self._theme_combo.setFixedWidth(_DROP_W)
        self._theme_combo.addItem("浅色", "light")
        self._theme_combo.addItem("深色", "dark")
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == self._config.theme:
                self._theme_combo.setCurrentIndex(i)
                break
        self._minimize_cb = QCheckBox("最小化到托盘")
        self._minimize_cb.setChecked(self._config.minimize_to_tray)
        self._auto_start_cb = QCheckBox("开机自动启动")
        self._auto_start_cb.setChecked(self._config.auto_start)
        layout.addLayout(_hrow(QLabel("主题:"), self._theme_combo,
                                self._minimize_cb, self._auto_start_cb))

        # ── 任务列表 ──
        layout.addWidget(QLabel("<b>任务列表</b>"))
        self._page_size_combo = DropdownWidget()
        self._page_size_combo.setFixedWidth(80)
        for n in (20, 50, 100):
            self._page_size_combo.addItem(str(n), n)
        ps = self._config.get("general", "page_size", default=20)
        for i in range(self._page_size_combo.count()):
            if self._page_size_combo.itemData(i) == ps:
                self._page_size_combo.setCurrentIndex(i)
                break
        self._default_sort_combo = DropdownWidget()
        self._default_sort_combo.setObjectName("settingsSortCombo")
        self._default_sort_combo.setFixedWidth(_DROP_W)
        for key, label in [("urgency", "优先级"), ("status", "状态"), ("deadline", "截止时间"),
                            ("created", "创建时间"), ("title", "标题")]:
            self._default_sort_combo.addItem(label, key)
        cur_sort = self._config.get("general", "default_sort", default="urgency")
        idx = self._default_sort_combo.findData(cur_sort)
        if idx >= 0:
            self._default_sort_combo.setCurrentIndex(idx)
        self._heatmap_year = QSpinBox()
        self._heatmap_year.setRange(1900, 2200)
        self._heatmap_year.setValue(self._config.get("display", "heatmap_start_year", default=2025))
        layout.addLayout(_hrow(QLabel("每页:"), self._page_size_combo,
                                QLabel("排序:"), self._default_sort_combo,
                                QLabel("年份:"), self._heatmap_year))

        # ── 提醒 ──
        layout.addWidget(QLabel("<b>提醒</b>"))
        self._reminders_cb = QCheckBox("启用提醒")
        self._reminders_cb.setChecked(self._config.reminders_enabled)
        hours = max(1, self._config.reminder_intervals[0] // 60) if self._config.reminder_intervals else 1
        self._interval_edit = QLineEdit()
        self._interval_edit.setFixedWidth(60)
        self._interval_edit.setText(str(hours))
        self._interval_edit.setPlaceholderText("小时")
        qs = self._config.get("reminders", "quiet_hours_start", default="22:00")
        qe = self._config.get("reminders", "quiet_hours_end", default="08:00")
        self._quiet_start_edit = QLineEdit(qs)
        self._quiet_start_edit.setFixedWidth(70)
        self._quiet_start_edit.setPlaceholderText("HH:MM")
        self._quiet_end_edit = QLineEdit(qe)
        self._quiet_end_edit.setFixedWidth(70)
        self._quiet_end_edit.setPlaceholderText("HH:MM")
        layout.addLayout(_hrow(self._reminders_cb,
                                QLabel("间隔:"), self._interval_edit, QLabel("H"),
                                QLabel("安静:"), self._quiet_start_edit,
                                QLabel("—"), self._quiet_end_edit))

        # ── 归档 ──
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("<b>归档</b>"))
        header_row.addStretch()
        add_btn = QPushButton("新增分区")
        add_btn.clicked.connect(self._on_add_partition)
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        self._partition_table = QTableWidget(0, 7)
        self._partition_table.setHorizontalHeaderLabels(
            ["名称", "默认分区", "可见", "自动归档", "归档阈值(天)", "自动锁定(分)", "密码"]
        )
        hh = self._partition_table.horizontalHeader()
        # 名称: stretch; rest: fixed
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.resizeSection(1, 80)
        hh.resizeSection(2, 60)
        hh.resizeSection(3, 80)
        hh.resizeSection(4, 100)
        hh.resizeSection(5, 100)
        hh.resizeSection(6, 60)
        for c in (1, 2, 3, 4, 5, 6):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        self._partition_table.verticalHeader().hide()
        self._partition_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._partition_table.setAlternatingRowColors(True)
        self._partition_table.setShowGrid(True)
        self._partition_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._partition_table.customContextMenuRequested.connect(self._on_table_context_menu)
        layout.addWidget(self._partition_table, stretch=1)

        # ── 激励语 ──
        layout.addWidget(QLabel("<b>激励语</b>"))
        from PySide6.QtWidgets import QFormLayout
        motd_form = QFormLayout()
        motd_form.setSpacing(4)
        motd = self._config.get("motd", default={})
        self._motd_edits: dict[str, QLineEdit] = {}
        for key, label_text in [("today", "今日无事时"), ("week", "本周无事时"),
                                 ("overdue", "无逾期时"), ("all", "全部为空时")]:
            edit = QLineEdit()
            edit.setText(motd.get(key, ""))
            edit.setPlaceholderText("输入激励语…")
            self._motd_edits[key] = edit
            motd_form.addRow(label_text + ":", edit)
        layout.addLayout(motd_form)

        layout.addStretch()
        self._populate_partition_table()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    # Partition table
    # ------------------------------------------------------------------

    def _populate_partition_table(self) -> None:
        self._partitions_data = self._repository.get_all_partitions()
        hidden = set(self._config.get("general", "hidden_partitions", default=[]))
        default_id = self._config.get("general", "default_partition", default="")

        self._partition_table.setRowCount(0)

        for p in self._partitions_data:
            row = self._partition_table.rowCount()
            self._partition_table.insertRow(row)
            pid = p["id"]

            # 0: 名称
            name_item = QTableWidgetItem(p["name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._partition_table.setItem(row, 0, name_item)

            # 1: 默认分区 — QCheckBox 居中
            def_cb = QCheckBox()
            def_cb.setChecked(pid == default_id)
            def_cb.toggled.connect(lambda checked, r=row: self._on_default_toggled(r, checked))
            self._partition_table.setCellWidget(row, 1, _wrap_center(def_cb))

            # 2: 可见 — QCheckBox 居中
            vis_cb = QCheckBox()
            vis_cb.setChecked(pid not in hidden)
            self._partition_table.setCellWidget(row, 2, _wrap_center(vis_cb))

            # 3: 自动归档 — QCheckBox 居中
            auto_cb = QCheckBox()
            auto_cb.setChecked(p.get("archive_enabled", 0) == 1)
            self._partition_table.setCellWidget(row, 3, _wrap_center(auto_cb))

            # 4: 归档阈值(天)
            days_edit = QLineEdit(str(p.get("archive_days", 9999)))
            days_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            days_edit.setMinimumWidth(60)
            self._partition_table.setCellWidget(row, 4, days_edit)

            # 5: 自动锁定(分)
            lock_edit = QLineEdit(str(p.get("auto_lock_minutes", 3)))
            lock_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lock_edit.setMinimumWidth(60)
            self._partition_table.setCellWidget(row, 5, lock_edit)

            # 6: 密码 — 🔒/🔓 按钮，主题色适配
            tokens = get_tokens()
            has_pwd = bool(p.get("password", ""))
            pwd_btn = QPushButton("🔒" if has_pwd else "🔓")
            pwd_btn.setFlat(True)
            pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            color = tokens.accent if has_pwd else tokens.text_secondary
            pwd_btn.setStyleSheet(
                f"QPushButton {{ font-size: 14px; color: {color}; border: none; background: transparent; }}"
            )
            pwd_btn.clicked.connect(
                lambda checked=False, pid=pid: self._on_set_partition_password(pid)
            )
            self._partition_table.setCellWidget(row, 6, _wrap_center(pwd_btn))

        self._partition_table.verticalHeader().setDefaultSectionSize(40)
        n = max(1, self._partition_table.rowCount())
        h = self._partition_table.horizontalHeader().height() + n * 40 + 4
        self._partition_table.setMinimumHeight(h)

    def _on_default_toggled(self, row: int, checked: bool) -> None:
        """Mutually exclusive default partition: uncheck all others."""
        if not checked:
            return  # prevent unchecking the default
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

    def _on_table_context_menu(self, pos) -> None:
        item = self._partition_table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        if row < 0 or row >= len(self._partitions_data):
            return
        p = self._partitions_data[row]
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_default = menu.addAction("设为默认分区")
        menu.addSeparator()
        act_rename = menu.addAction("重命名")
        act_password = menu.addAction("设置密码")
        menu.addSeparator()
        act_delete = menu.addAction("删除")
        action = menu.exec(self._partition_table.viewport().mapToGlobal(pos))
        if action == act_default:
            def_w = self._partition_table.cellWidget(row, 1)
            if def_w:
                def_cb = def_w.findChild(QCheckBox)
                if def_cb:
                    def_cb.setChecked(True)
        elif action == act_rename:
            self._on_rename_row(row)
        elif action == act_password:
            self._on_set_partition_password(p["id"])
        elif action == act_delete:
            self._on_delete_single_partition(p["id"])

    def _on_rename_row(self, row: int) -> None:
        p = self._partitions_data[row]
        name, ok = QInputDialog.getText(self, "重命名分区", "新名称：", text=p["name"])
        if ok and name.strip():
            self._repository.upsert_partition(name.strip(), partition_id=p["id"])
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    def _on_add_partition(self) -> None:
        name, ok = QInputDialog.getText(self, "新增分区", "分区名称：")
        if ok and name.strip():
            self._repository.upsert_partition(name.strip())
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    def _on_delete_single_partition(self, pid: str) -> None:
        for p in self._partitions_data:
            if p["id"] == pid:
                count = self._repository.count_tasks_in_partition(pid)
                if count > 0:
                    QMessageBox.warning(
                        self, "无法删除",
                        f'分区 "{p["name"]}" 中还有 {count} 个任务，请先清空后再删除。',
                    )
                    return
                self._confirm_delete_partition(p)
                return

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

    def _confirm_delete_partition(self, p: dict) -> None:
        result = QMessageBox.question(
            self, "确认删除",
            f'确定要删除分区 "{p["name"]}" 吗？\n该分区下的任务将变为"未分类"。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._repository.delete_partition(p["id"])
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    def showEvent(self, event) -> None:
        """Apply dark title bar on Windows when the current theme is dark."""
        super().showEvent(event)
        if is_dark_mode_supported() and is_dark():
            set_window_dark_mode(self, True, caption_color=get_surface_color())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_time(text: str) -> bool:
        return bool(re.match(r"^\d{1,2}:\d{2}$", text))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        self._config.set("general", "minimize_to_tray", value=self._minimize_cb.isChecked())
        self._config.set("general", "auto_start", value=self._auto_start_cb.isChecked())
        from ...utils.win32_autostart import set_autostart
        set_autostart(self._auto_start_cb.isChecked())
        self._config.set("general", "page_size", value=self._page_size_combo.currentData())
        self._config.set("general", "default_sort", value=self._default_sort_combo.currentData())
        self._config.set("display", "theme", value=self._theme_combo.currentData())
        self._config.set("display", "heatmap_start_year", value=self._heatmap_year.value())
        self._config.set("reminders", "enabled", value=self._reminders_cb.isChecked())
        try:
            hours = int(self._interval_edit.text().strip())
            if hours <= 0:
                hours = 1
        except ValueError:
            hours = 1
        self._config.set("reminders", "intervals_minutes", value=[hours * 60])
        qs = self._quiet_start_edit.text().strip()
        qe = self._quiet_end_edit.text().strip()
        if self._validate_time(qs):
            self._config.set("reminders", "quiet_hours_start", value=qs)
        if self._validate_time(qe):
            self._config.set("reminders", "quiet_hours_end", value=qe)
        hidden = []
        for r in range(self._partition_table.rowCount()):
            pid = self._partitions_data[r]["id"]
            vis_w = self._partition_table.cellWidget(r, 2)
            if vis_w:
                vis_cb = vis_w.findChild(QCheckBox)
                if vis_cb and not vis_cb.isChecked():
                    hidden.append(pid)
            auto_w = self._partition_table.cellWidget(r, 3)
            if auto_w:
                auto_cb = auto_w.findChild(QCheckBox)
                if auto_cb:
                    self._repository.update_partition_archive_enabled(
                        pid, 1 if auto_cb.isChecked() else 0
                    )
            days_w = self._partition_table.cellWidget(r, 4)
            if days_w:
                try:
                    days = max(0, int(days_w.text().strip()))
                except ValueError:
                    days = 9999
                self._repository.update_partition_archive_days(pid, days)
            lock_w = self._partition_table.cellWidget(r, 5)
            if lock_w:
                try:
                    lock_mins = max(0, int(lock_w.text().strip()))
                except ValueError:
                    lock_mins = 3
                self._repository.update_partition_auto_lock(pid, lock_mins)
        self._config.set("general", "hidden_partitions", value=hidden)
        motd_cfg = {}
        for key, edit in self._motd_edits.items():
            if edit.text().strip():
                motd_cfg[key] = edit.text().strip()
        self._config.set("motd", value=motd_cfg)
        self._config.save()
        self.accept()

    def theme_changed(self) -> bool:
        return self._theme_combo.currentData() != "system"
