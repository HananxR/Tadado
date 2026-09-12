"""NavShell — 常驻侧边栏：按分组渲染视图注册表入口。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ..utils.design_tokens import get_tokens
from ..utils.icon_loader import load_icon
from .views import VIEW_REGISTRY


def _rgba(hex_color: str, alpha: float) -> str:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


class NavShell(QWidget):
    """Vertical icon rail: grouped page buttons + settings gear at bottom.

    点击 / Ctrl+1..5 → ``page_requested(page_id)``；激活态由 ``set_active`` 控制。
    """

    page_requested = Signal(str)
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(64)
        self._buttons: dict[str, QPushButton] = {}
        self._active: str | None = None
        self._build()
        self._shortcuts: list[QShortcut] = []
        for i, page_id in enumerate(list(VIEW_REGISTRY.keys()), start=1):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda pid=page_id: self.set_active(pid, emit=True))
            self._shortcuts.append(sc)

    def _build(self) -> None:
        t = get_tokens()
        accent = t.accent
        self.setObjectName("navShell")
        self.setStyleSheet(
            f"QPushButton[navPage] {{ border: none; border-radius: 10px; background: transparent; }}"
            f"QPushButton[navPage]:hover {{ background: {_rgba(accent, 0.10)}; }}"
            f'QPushButton[navPage][active="true"] {{'
            f" background: {_rgba(accent, 0.20)}; border-left: 3px solid {accent}; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 10)
        layout.setSpacing(3)

        current_group: str | None = None
        for i, spec in enumerate(VIEW_REGISTRY.values(), start=1):
            if spec.group != current_group:
                current_group = spec.group
                label = QLabel(spec.group)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet(
                    f"color: {t.text_secondary}; font-size: 9px; letter-spacing: 1.5px;"
                    " background: transparent; margin-top: 8px; margin-bottom: 2px;"
                )
                layout.addWidget(label)
            btn = QPushButton()
            btn.setProperty("navPage", True)
            btn.setIcon(load_icon(spec.icon))
            btn.setIconSize(QSize(19, 19))
            btn.setFixedSize(42, 42)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{spec.title} (Ctrl+{i})")
            btn.clicked.connect(lambda _checked=False, pid=spec.id: self.set_active(pid, emit=True))
            self._buttons[spec.id] = btn
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch()

        # 底部设置入口（Phase 1：分区选择器仍留状态栏）
        self._settings_btn = QPushButton()
        self._settings_btn.setProperty("navPage", True)
        self._settings_btn.setIcon(load_icon("settings"))
        self._settings_btn.setIconSize(QSize(19, 19))
        self._settings_btn.setFixedSize(42, 42)
        self._settings_btn.setFlat(True)
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setToolTip("设置")
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self._settings_btn, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_active(self, page_id: str, emit: bool = False) -> None:
        """高亮指定页面；emit=True 时发出 page_requested（点击/快捷键路径）。"""
        if page_id not in self._buttons:
            return
        self._active = page_id
        for pid, btn in self._buttons.items():
            btn.setProperty("active", pid == page_id)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if emit:
            self.page_requested.emit(page_id)

    @property
    def active(self) -> str | None:
        return self._active
