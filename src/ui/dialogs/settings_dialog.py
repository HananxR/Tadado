"""Application settings dialog with tabbed interface."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig
from ...models.repository import TaskRepository
from ...utils.signal_bus import get_signal_bus


class SettingsDialog(QDialog):
    """Settings dialog with tabs for General, Display, Reminders, Archive, and Partitions."""

    def __init__(
        self, config: AppConfig, repository: TaskRepository, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._repository = repository
        self._original_theme = config.theme

        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.resize(500, 450)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "通用")
        tabs.addTab(self._build_display_tab(), "显示")
        tabs.addTab(self._build_reminders_tab(), "提醒")
        tabs.addTab(self._build_archive_tab(), "归档")
        tabs.addTab(self._build_partitions_tab(), "分区管理")
        tabs.addTab(self._build_motd_tab(), "激励语")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # General tab
    # ------------------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._minimize_cb = QCheckBox()
        self._minimize_cb.setChecked(self._config.minimize_to_tray)
        form.addRow("最小化到托盘", self._minimize_cb)

        self._auto_lock_spin = QSpinBox()
        self._auto_lock_spin.setRange(1, 120)
        self._auto_lock_spin.setSuffix(" 分钟")
        self._auto_lock_spin.setValue(
            self._config.get("general", "auto_lock_minutes", default=10)
        )
        form.addRow("分区自动锁定", self._auto_lock_spin)

        self._page_size_spin = QSpinBox()
        self._page_size_spin.setRange(10, 100)
        self._page_size_spin.setSingleStep(10)
        self._page_size_spin.setSuffix(" 条/页")
        self._page_size_spin.setValue(
            self._config.get("general", "page_size", default=20)
        )
        form.addRow("默认每页条数", self._page_size_spin)

        return w

    # ------------------------------------------------------------------
    # Display tab
    # ------------------------------------------------------------------

    def _build_display_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem("跟随系统", "system")
        self._theme_combo.addItem("浅色", "light")
        self._theme_combo.addItem("深色", "dark")
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == self._config.theme:
                self._theme_combo.setCurrentIndex(i)
                break
        form.addRow("主题", self._theme_combo)

        start_year = self._config.get("display", "heatmap_start_year", default=2026)
        self._heatmap_start_year = QSpinBox()
        self._heatmap_start_year.setRange(2000, 2100)
        self._heatmap_start_year.setValue(start_year)
        form.addRow("热力图起始年份", self._heatmap_start_year)

        return w

    # ------------------------------------------------------------------
    # Reminders tab
    # ------------------------------------------------------------------

    def _build_reminders_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._reminders_cb = QCheckBox()
        self._reminders_cb.setChecked(self._config.reminders_enabled)
        form.addRow("启用提醒", self._reminders_cb)

        self._quiet_start = QTimeEdit()
        parts = self._config.get("reminders", "quiet_hours_start", default="22:00").split(":")
        from PySide6.QtCore import QTime
        self._quiet_start.setTime(QTime(int(parts[0]), int(parts[1])))
        form.addRow("安静时段开始", self._quiet_start)

        self._quiet_end = QTimeEdit()
        parts = self._config.get("reminders", "quiet_hours_end", default="08:00").split(":")
        self._quiet_end.setTime(QTime(int(parts[0]), int(parts[1])))
        form.addRow("安静时段结束", self._quiet_end)

        return w

    # ------------------------------------------------------------------
    # Archive tab
    # ------------------------------------------------------------------

    def _build_archive_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        self._archive_cb = QCheckBox()
        self._archive_cb.setChecked(self._config.archive_enabled)
        form.addRow("启用自动归档", self._archive_cb)

        self._archive_days = QSpinBox()
        self._archive_days.setRange(1, 365)
        self._archive_days.setValue(self._config.archive_after_days)
        form.addRow("完成后天数", self._archive_days)

        return w

    # ------------------------------------------------------------------
    # Fields tab (status / priority configuration)
    # ------------------------------------------------------------------

    def _build_fields_tab(self) -> QWidget:
        from ...models.task_status import TaskStatus
        from ...models.priority import Priority

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        sub_tabs = QTabWidget()

        # --- Status sub-tab ---
        sw = QWidget()
        sw_layout = QVBoxLayout(sw)
        self._status_table = QTableWidget(0, 3)
        self._status_table.setHorizontalHeaderLabels(["关键字", "显示名", "颜色"])
        self._status_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        sw_layout.addWidget(self._status_table)

        s_btn_row = QHBoxLayout()
        s_add = QPushButton("添加")
        s_add.clicked.connect(self._on_add_status)
        s_reset = QPushButton("恢复默认")
        s_reset.clicked.connect(self._on_reset_statuses)
        s_btn_row.addWidget(s_add)
        s_btn_row.addWidget(s_reset)
        s_btn_row.addStretch()
        sw_layout.addLayout(s_btn_row)
        sub_tabs.addTab(sw, "状态配置")

        # --- Priority sub-tab ---
        pw = QWidget()
        pw_layout = QVBoxLayout(pw)
        self._priority_table = QTableWidget(0, 3)
        self._priority_table.setHorizontalHeaderLabels(["等级", "显示名", "颜色"])
        self._priority_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        pw_layout.addWidget(self._priority_table)

        p_btn_row = QHBoxLayout()
        p_add = QPushButton("添加")
        p_add.clicked.connect(self._on_add_priority)
        p_reset = QPushButton("恢复默认")
        p_reset.clicked.connect(self._on_reset_priorities)
        p_btn_row.addWidget(p_add)
        p_btn_row.addWidget(p_reset)
        p_btn_row.addStretch()
        pw_layout.addLayout(p_btn_row)
        sub_tabs.addTab(pw, "优先级配置")

        layout.addWidget(sub_tabs)
        self._populate_status_table()
        self._populate_priority_table()
        return w

    def _populate_status_table(self) -> None:
        from ...models.task_status import TaskStatus
        self._status_table.setRowCount(0)
        custom = self._config.get("statuses", default={})
        for s in TaskStatus:
            row = self._status_table.rowCount()
            self._status_table.insertRow(row)
            kw_item = QTableWidgetItem(s.value)
            kw_item.setFlags(kw_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # built-in: read-only
            kw_item.setToolTip("内置")
            self._status_table.setItem(row, 0, kw_item)
            name = custom.get(s.value, {}).get("display_name", s.display_name)
            self._status_table.setItem(row, 1, QTableWidgetItem(name))
            color = custom.get(s.value, {}).get("display_color", s.display_color)
            self._status_table.setItem(row, 2, QTableWidgetItem(color))
        for kw, cfg in custom.items():
            if kw not in {s.value for s in TaskStatus}:
                row = self._status_table.rowCount()
                self._status_table.insertRow(row)
                self._status_table.setItem(row, 0, QTableWidgetItem(kw))
                self._status_table.setItem(row, 1, QTableWidgetItem(cfg.get("display_name", kw)))
                self._status_table.setItem(row, 2, QTableWidgetItem(cfg.get("display_color", "#888")))

    def _populate_priority_table(self) -> None:
        from ...models.priority import Priority
        self._priority_table.setRowCount(0)
        custom = self._config.get("priorities", default={})
        for p in Priority:
            if p == Priority.NONE:
                continue
            row = self._priority_table.rowCount()
            self._priority_table.insertRow(row)
            kw_item = QTableWidgetItem(str(p.value))
            kw_item.setFlags(kw_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            kw_item.setToolTip("内置")
            self._priority_table.setItem(row, 0, kw_item)
            name = custom.get(str(p.value), {}).get("display_name", p.name)
            self._priority_table.setItem(row, 1, QTableWidgetItem(name))
            color = custom.get(str(p.value), {}).get("display_color", p.display_color)
            self._priority_table.setItem(row, 2, QTableWidgetItem(color))
        for lvl, cfg in custom.items():
            if int(lvl) not in {p.value for p in Priority}:
                row = self._priority_table.rowCount()
                self._priority_table.insertRow(row)
                self._priority_table.setItem(row, 0, QTableWidgetItem(lvl))
                self._priority_table.setItem(row, 1, QTableWidgetItem(cfg.get("display_name", lvl)))
                self._priority_table.setItem(row, 2, QTableWidgetItem(cfg.get("display_color", "#888")))

    def _on_add_status(self) -> None:
        kw, ok = QInputDialog.getText(self, "添加状态", "关键字 (大写字母)：")
        if ok and kw.strip():
            row = self._status_table.rowCount()
            self._status_table.insertRow(row)
            self._status_table.setItem(row, 0, QTableWidgetItem(kw.strip().upper()))
            self._status_table.setItem(row, 1, QTableWidgetItem(kw.strip()))
            self._status_table.setItem(row, 2, QTableWidgetItem("#888888"))

    def _on_reset_statuses(self) -> None:
        self._config.set("statuses", value={})
        self._populate_status_table()

    def _on_add_priority(self) -> None:
        lvl, ok = QInputDialog.getText(self, "添加优先级", "等级数字 (4+)：")
        if ok and lvl.strip().isdigit():
            row = self._priority_table.rowCount()
            self._priority_table.insertRow(row)
            self._priority_table.setItem(row, 0, QTableWidgetItem(lvl.strip()))
            self._priority_table.setItem(row, 1, QTableWidgetItem(lvl.strip()))
            self._priority_table.setItem(row, 2, QTableWidgetItem("#888888"))

    def _on_reset_priorities(self) -> None:
        self._config.set("priorities", value={})
        self._populate_priority_table()

    # ------------------------------------------------------------------
    # Partitions tab
    # ------------------------------------------------------------------

    def _build_partitions_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        hint = QLabel("勾选的分区将显示在筛选栏中，取消勾选可隐藏分区。")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        # Partition table: 可见 | 名称 | 密码 | 删除
        self._partition_table = QTableWidget(0, 4)
        self._partition_table.setHorizontalHeaderLabels(["可见", "名称", "密码", ""])
        self._partition_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._partition_table.horizontalHeader().resizeSection(0, 40)
        self._partition_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._partition_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._partition_table.horizontalHeader().resizeSection(2, 60)
        self._partition_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self._partition_table.horizontalHeader().resizeSection(3, 60)
        self._partition_table.verticalHeader().hide()
        self._partition_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._partition_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._on_add_partition)
        rename_btn = QPushButton("重命名")
        rename_btn.clicked.connect(self._on_rename_partition)
        delete_btn = QPushButton("删除")
        delete_btn.clicked.connect(self._on_delete_partition)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rename_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        default_label = QLabel("默认分区：")
        self._default_partition_combo = QComboBox()
        layout.addWidget(default_label)
        layout.addWidget(self._default_partition_combo)

        self._populate_partition_table()
        return w

    def _populate_partition_table(self) -> None:
        self._partitions_data = self._repository.get_all_partitions()
        hidden = set(self._config.get("general", "hidden_partitions", default=[]))
        default_id = self._config.get("general", "default_partition", default="")

        self._partition_table.setRowCount(0)
        self._default_partition_combo.blockSignals(True)
        self._default_partition_combo.clear()
        self._default_partition_combo.addItem("(无)", "")

        for i, p in enumerate(self._partitions_data):
            row = self._partition_table.rowCount()
            self._partition_table.insertRow(row)

            # Visible checkbox
            cb = QCheckBox()
            cb.setChecked(p["id"] not in hidden)
            self._partition_table.setCellWidget(row, 0, cb)

            # Name
            name_item = QTableWidgetItem(p["name"])
            self._partition_table.setItem(row, 1, name_item)

            # Password button
            has_pwd = bool(p.get("password", ""))
            pwd_btn = QPushButton("🔒" if has_pwd else "🔓")
            pwd_btn.setStyleSheet(
                "QPushButton { font-size: 12px; padding: 2px 6px; border: none; background: transparent; }"
            )
            pwd_btn.clicked.connect(lambda checked=False, pid=p["id"]: self._on_set_partition_password(pid))
            self._partition_table.setCellWidget(row, 2, pwd_btn)

            # Delete button per row
            del_btn = QPushButton("删除")
            del_btn.setStyleSheet("QPushButton { color: #c0392b; font-size: 10px; padding: 2px 6px; }")
            del_btn.clicked.connect(lambda checked=False, pid=p["id"]: self._on_delete_single_partition(pid))
            self._partition_table.setCellWidget(row, 3, del_btn)

            # Default combo
            self._default_partition_combo.addItem(p["name"], p["id"])
            if p["id"] == default_id:
                self._default_partition_combo.setCurrentIndex(i + 1)

        self._default_partition_combo.blockSignals(False)

    def _on_add_partition(self) -> None:
        name, ok = QInputDialog.getText(self, "添加分区", "分区名称：")
        if ok and name.strip():
            self._repository.upsert_partition(name.strip())
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    def _on_rename_partition(self) -> None:
        row = self._partition_table.currentRow()
        if row < 0 or row >= len(self._partitions_data):
            return
        p = self._partitions_data[row]
        name, ok = QInputDialog.getText(self, "重命名分区", "新名称：", text=p["name"])
        if ok and name.strip():
            self._repository.upsert_partition(name.strip(), partition_id=p["id"])
            self._populate_partition_table()
            get_signal_bus().partitions_changed.emit()

    def _on_delete_partition(self) -> None:
        row = self._partition_table.currentRow()
        if row < 0 or row >= len(self._partitions_data):
            return
        p = self._partitions_data[row]
        self._confirm_delete_partition(p)

    def _on_delete_single_partition(self, pid: str) -> None:
        for p in self._partitions_data:
            if p["id"] == pid:
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
                # Empty = clear password
                self._repository.set_partition_password(pid, "")
            elif old != cur:
                # Wrong password — offer reset
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
                # Correct password — change it
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

    # ------------------------------------------------------------------
    # MOTD tab (encouragement messages)
    # ------------------------------------------------------------------

    def _build_motd_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(10)

        motd = self._config.get("motd", default={})
        labels = [
            ("today", "今日无事时："),
            ("week", "本周无事时："),
            ("overdue", "无逾期时："),
            ("all", "全部为空时："),
        ]
        self._motd_edits: dict[str, QLineEdit] = {}
        for key, label_text in labels:
            edit = QLineEdit()
            edit.setText(motd.get(key, ""))
            edit.setPlaceholderText("输入激励语…")
            self._motd_edits[key] = edit
            form.addRow(label_text, edit)

        return w

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        self._config.set("general", "minimize_to_tray", value=self._minimize_cb.isChecked())
        self._config.set("general", "auto_lock_minutes", value=self._auto_lock_spin.value())
        self._config.set("general", "page_size", value=self._page_size_spin.value())
        self._config.set("display", "theme", value=self._theme_combo.currentData())
        self._config.set("display", "heatmap_start_year", value=self._heatmap_start_year.value())
        self._config.set("reminders", "enabled", value=self._reminders_cb.isChecked())
        self._config.set(
            "reminders", "quiet_hours_start",
            value=self._quiet_start.time().toString("HH:mm"),
        )
        self._config.set(
            "reminders", "quiet_hours_end",
            value=self._quiet_end.time().toString("HH:mm"),
        )
        self._config.set("archive", "enabled", value=self._archive_cb.isChecked())
        self._config.set("archive", "completed_after_days", value=self._archive_days.value())
        self._config.set(
            "general", "default_partition",
            value=self._default_partition_combo.currentData(),
        )
        # Save hidden partitions
        hidden = []
        for r in range(self._partition_table.rowCount()):
            cb = self._partition_table.cellWidget(r, 0)
            if cb and not cb.isChecked():
                pid = self._partitions_data[r]["id"]
                hidden.append(pid)
        self._config.set("general", "hidden_partitions", value=hidden)

        motd_cfg = {}
        for key, edit in self._motd_edits.items():
            if edit.text().strip():
                motd_cfg[key] = edit.text().strip()
        self._config.set("motd", value=motd_cfg)

        self._config.save()
        self.accept()

    def theme_changed(self) -> bool:
        """Return True if the theme was changed."""
        return self._theme_combo.currentData() != "system"
