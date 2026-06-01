"""Statistics summary panel for the calendar heatmap."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ...utils.design_tokens import get_tokens


class _StatCard(QWidget):
    """A single stat: large value + small label below."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        self._desc_label = QLabel(label)
        self._desc_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._desc_label)

        self._value_label = QLabel("--")
        self._value_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(self._value_label)

        layout.addStretch()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)


class HeatmapStatsPanel(QWidget):
    """Horizontal row of stat cards: total, active days, longest streak, daily avg."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("heatmapStatsPanel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        self._total_card = _StatCard("总任务")
        self._active_card = _StatCard("活跃天数")
        self._streak_card = _StatCard("最长连续")
        self._avg_card = _StatCard("日均")

        layout.addWidget(self._total_card)
        layout.addWidget(self._active_card)
        layout.addWidget(self._streak_card)
        layout.addWidget(self._avg_card)
        layout.addStretch()

    def refresh(
        self,
        total: int,
        active_days: int,
        longest_streak: int,
        daily_avg: float,
    ) -> None:
        self._total_card.set_value(f"{total}个")
        self._active_card.set_value(f"{active_days}天")
        self._streak_card.set_value(f"{longest_streak}天")
        self._avg_card.set_value(f"{daily_avg:.1f}个")
