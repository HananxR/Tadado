"""Carousel banner — horizontally scrolling groups of priority + completed tasks."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class CarouselBanner(QWidget):
    """Auto-scrolling banner showing recent tasks.

    Displays up to *max_items* tasks, scrolling in groups of *group_size*.
    Each group is shown as horizontal labels side by side.
    """

    task_clicked = Signal(str)  # task_id

    def __init__(
        self,
        max_items: int = 10,
        group_size: int = 3,
        interval_seconds: int = 5,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._max_items = max_items
        self._group_size = max(group_size, 1)
        self._interval = interval_seconds * 1000
        self._items: list[dict] = []
        self._current_offset = 0

        self.setObjectName("carouselBanner")
        self.setMinimumHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 0, 2)
        layout.setSpacing(14)

        self._labels: list[QLabel] = []
        for _ in range(self._group_size):
            lbl = QLabel()
            lbl.setStyleSheet(
                "QLabel { color: #555; font-size: 11px; background: transparent; }"
            )
            lbl.setWordWrap(False)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda e, idx=len(self._labels): self._on_label_clicked(idx)
            self._labels.append(lbl)
            layout.addWidget(lbl)

        layout.addStretch()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._timer.start(self._interval)

    def set_items(self, items: list[dict]) -> None:
        """Set carousel items. Each item: {task_id, text, color}."""
        self._items = items[:self._max_items]
        self._current_offset = 0
        self._render()

    def _scroll(self) -> None:
        n = len(self._items)
        if n <= self._group_size:
            return  # no need to scroll when items fit in one view
        self._current_offset = (self._current_offset + self._group_size) % n
        self._render()

    def _render(self) -> None:
        n = len(self._items)
        shown = min(n, self._group_size)
        for i in range(self._group_size):
            lbl = self._labels[i]
            if i < shown:
                idx = (self._current_offset + i) % max(n, 1)
                item = self._items[idx]
                color = item.get("color", "#5b8def")
                text = item.get("text", "")
                lbl.setText(f'<span style="color:{color};">●</span> {text}')
                lbl.setToolTip(text)
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

    def _on_label_clicked(self, label_idx: int) -> None:
        n = len(self._items)
        if n == 0:
            return
        idx = (self._current_offset + label_idx) % n
        item = self._items[idx]
        tid = item.get("task_id", "")
        if tid:  # skip placeholder entries
            self.task_clicked.emit(tid)
