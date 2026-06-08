"""Collapsible panel wrapper for the calendar heatmap — minimal chrome."""

from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget


class HeatmapCollapsePanel(QWidget):
    """Wraps CalendarHeatmapWidget. Visibility toggled by MainWindow."""

    def __init__(self, heatmap_widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(heatmap_widget)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def refresh(self) -> None:
        w = self.findChild(QWidget)
        if w and hasattr(w, "refresh"):
            w.refresh()
