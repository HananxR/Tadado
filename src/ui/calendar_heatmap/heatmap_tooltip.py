"""Rich hover tooltip card that follows the mouse cursor."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


class HeatmapTooltip(QDialog):
    """Frameless tooltip showing date + activity count + task count."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.ToolTip
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setObjectName("heatmapTooltip")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._date_label = QLabel()
        self._date_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(self._date_label)

        self._info_label = QLabel()
        self._info_label.setStyleSheet("font-size: 11px;")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        self.adjustSize()

    def show_for_date(
        self,
        screen_pos: QPoint,
        d: date,
        entry_count: int,
        task_count: int = 0,
    ) -> None:
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        wd = weekdays[d.weekday()]
        self._date_label.setText(f"{d.year}年{d.month}月{d.day}日 周{wd}")

        if entry_count > 0:
            self._info_label.setText(
                f"当日 {entry_count} 条记录，涉及 {task_count} 个任务"
            )
        else:
            self._info_label.setText("当日暂无工作记录")

        self.adjustSize()
        self.setMinimumHeight(self.sizeHint().height())

        x = screen_pos.x() + 16
        y = screen_pos.y() + 16
        screen = self.screen()
        if screen:
            geom = screen.availableGeometry()
            if x + self.width() > geom.right():
                x = screen_pos.x() - self.width() - 8
            if y + self.height() > geom.bottom():
                y = screen_pos.y() - self.height() - 8
        self.move(x, y)
        self.show()

    def hide_tip(self) -> None:
        self.hide()
