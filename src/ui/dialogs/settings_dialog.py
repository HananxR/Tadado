"""Application settings dialog with tabbed interface."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ...config import AppConfig


class SettingsDialog(QDialog):
    """Settings dialog with tabs for General, Display, Reminders, and Archive."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._original_theme = config.theme

        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.resize(480, 400)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "通用")
        tabs.addTab(self._build_display_tab(), "显示")
        tabs.addTab(self._build_reminders_tab(), "提醒")
        tabs.addTab(self._build_archive_tab(), "归档")
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

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 24)
        self._font_size.setValue(self._config.font_size)
        form.addRow("字体大小", self._font_size)

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
    # Save
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        self._config.set("general", "minimize_to_tray", value=self._minimize_cb.isChecked())
        self._config.set("display", "theme", value=self._theme_combo.currentData())
        self._config.set("display", "font_size", value=self._font_size.value())
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
        self._config.save()
        self.accept()

    def theme_changed(self) -> bool:
        """Return True if the theme was changed."""
        return self._theme_combo.currentData() != "system"
