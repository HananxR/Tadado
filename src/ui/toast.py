"""Toast — 底部居中的浮层提示（对齐原型 ``#toast``）。

原型**没有底部状态栏**：所有操作反馈都用「底部居中 + 反色 + 自动淡出」的
浮层。原先这些消息写在 ``QStatusBar`` 里，与侧栏分区入口、时钟挤在同一
条栏上，视觉上很杂。

样式对照原型：

.. code-block:: css

    #toast { position: fixed; left: 50%; bottom: 26px;
             background: var(--text); color: var(--bg);
             padding: 9px 16px; border-radius: 9px;
             transition: all .25s ease; }
    #toast.show { opacity: 1; }
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from ..utils.design_tokens import get_tokens

#: 浮层距父容器底部的距离（原型 ``bottom: 26px``）
BOTTOM_MARGIN = 26
#: 淡入 / 淡出时长（原型 ``transition: .25s``）
FADE_MS = 200
#: 默认停留时长（原型 ``setTimeout(toast, 2200)``）
DEFAULT_MS = 2200


class Toast(QLabel):
    """A transient, click-through message pill anchored to the bottom centre.

    The widget is a child of the main window (not a top-level popup), so it
    must be re-positioned whenever the window is resized — see
    :meth:`reposition`.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 纯展示层：绝不拦截鼠标事件
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(FADE_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._fade(0.0))

        self.refresh_theme()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def refresh_theme(self) -> None:
        """Re-apply the inverted pill style for the current theme."""
        t = get_tokens()
        self.setStyleSheet(
            f"QLabel#toast {{ background: {t.text_primary}; color: {t.bg_primary};"
            " border-radius: 9px; padding: 9px 16px; font-size: 12px; }"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_message(self, message: str, ms: int = DEFAULT_MS) -> None:
        """Show *message* for *ms* milliseconds, then fade out."""
        self.setText(message)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(ms)
        self._fade(1.0)

    def reposition(self) -> None:
        """Keep the pill centred just above the bottom edge of the parent."""
        parent = self.parentWidget()
        if parent is None:
            return
        x = max(0, (parent.width() - self.width()) // 2)
        y = max(0, parent.height() - self.height() - BOTTOM_MARGIN)
        self.move(x, y)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fade(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        # 淡出结束后彻底隐藏，避免留下一个空的可视层
        if self._effect.opacity() <= 0.01:
            self.hide()
