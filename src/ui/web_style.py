"""QProxyStyle: 接管 Fusion 画不好 / 画不了的那几处绘制。

为什么需要这一层
----------------
QSS 只能覆盖**已有**的绘制分支，无法新增绘制。Fusion 有两件招牌在 QSS 里
根本够不着，而它们恰恰是最扎眼的「非 web」信号：

1. 焦点虚框（``PE_FrameFocusRect``）。QSS 只有 ``outline`` 能把它整块关掉，
   没法改成 web ``:focus-visible`` 那种「2px 实线圆角环」。但直接关掉会让
   键盘用户彻底失去焦点提示，所以必须**替换**而不是**移除**。
2. 下拉箭头。它有**两条互斥通道**，实测：

      无 QSS            -> drawComplexControl(CC_ComboBox)
      套了 base.qss     -> drawPrimitive(PE_IndicatorArrowDown)

   第二条正是为什么 ``::down-arrow`` 在 QSS 里只能换 ``image``（一张位图），
   既无法描边、也无法跟随主题变色。所以下面两条通道都接，且互斥不会重影。

因此这一层不是「又一块 QSS 补丁」，而是**在 Fusion 之上接管绘制**：只处理
Fusion 够不着的部件，其余照旧交给 Fusion + QSS。
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleOptionComboBox

from ..utils.design_tokens import get_tokens

__all__ = ["WebStyle"]


class WebStyle(QProxyStyle):
    """Fusion 之上的一层薄代理，只替换 Fusion 改不掉的两处绘制。

    为什么仍以 Fusion 为底：Windows 原生风格（``windows11`` / ``windowsvista``）
    会让下拉箭头、滚动条、SpinBox 子控件**完全无视 QSS**，主题就无从谈起；
    Fusion 是纯 Qt 自绘、完全听从 QSS 与调色板，是唯一可控的底座。
    """

    def __init__(self, base_style: str = "Fusion") -> None:
        super().__init__(base_style)

    # ── 绘制 ──────────────────────────────────────────────────────────
    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
            self._draw_focus_ring(option, painter)
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorArrowDown:
            self._draw_chevron(option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)

    def drawComplexControl(self, control, option, painter, widget=None) -> None:
        if control == QStyle.ComplexControl.CC_ComboBox:
            self._draw_combo(option, painter, widget)
            return
        super().drawComplexControl(control, option, painter, widget)

    # ── 度量 ──────────────────────────────────────────────────────────
    def pixelMetric(self, metric, option=None, widget=None) -> int:
        # 焦点环自己做了内缩，再让 Fusion 加边距会离控件太远。
        if metric in (
            QStyle.PixelMetric.PM_FocusFrameVMargin,
            QStyle.PixelMetric.PM_FocusFrameHMargin,
        ):
            return 0
        return super().pixelMetric(metric, option, widget)

    # ── 组合框：摘掉 Fusion 的实心三角，改画细线 chevron ──────────────
    # 仅在**无 QSS** 时被调用（套了 base.qss 时走上面的 drawPrimitive）。
    # 保留它是因为并非所有 QComboBox 都必然命中 QSS 规则。
    def _draw_combo(self, option, painter, widget=None) -> None:
        try:
            body = QStyleOptionComboBox(option)
        except TypeError:  # 不是 ComboBox 的 option，原样交给基类
            super().drawComplexControl(
                QStyle.ComplexControl.CC_ComboBox, option, painter, widget
            )
            return

        # 从 subControls 里摘掉箭头，避免基类再画一个实心三角（否则会出现
        # 两个箭头）。其余子控件（框、编辑区）照旧由基类绘制。
        #
        # 注意：这里**不能**写 ``subControls & ~SC_ComboBoxArrow``——Qt 枚举
        # 的 ``~`` 会取到枚举定义之外的位，再赋值回去会抛
        # "not a valid QStyle.SubControl"。只能用合法成员正向组合。
        arrow_sc = QStyle.SubControl.SC_ComboBoxArrow
        body.subControls = (
            QStyle.SubControl.SC_ComboBoxFrame
            | QStyle.SubControl.SC_ComboBoxEditField
        )
        super().drawComplexControl(
            QStyle.ComplexControl.CC_ComboBox, body, painter, widget
        )

        arrow = QStyleOptionComboBox(option)
        arrow.rect = self.subControlRect(
            QStyle.ComplexControl.CC_ComboBox, body, arrow_sc, widget
        )
        self._draw_chevron(arrow, painter)

    # ── 具体绘制 ──────────────────────────────────────────────────────
    @staticmethod
    def _draw_focus_ring(option, painter) -> None:
        """web ``:focus-visible`` 语义：仅键盘导航时给 2px 实线圆角环。

        Fusion 画的是 1px 黑色**虚线矩形**——那是最刺眼的「不像 web」信号。
        这里换成强调色实线圆角环；鼠标点击产生的焦点不画，与浏览器一致。
        """
        if not option.state & QStyle.StateFlag.State_KeyboardFocusChange:
            return
        t = get_tokens()
        rect = QRectF(option.rect).adjusted(1.0, 1.0, -1.0, -1.0)
        pen = QPen(QColor(t.accent))
        pen.setWidthF(2.0)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 5.0, 5.0)
        painter.restore()

    @staticmethod
    def _draw_chevron(option, painter) -> None:
        """原型 ``.dd-btn svg`` 的细线 chevron（11px / ``stroke-width:1.7``）。

        替换 Fusion 那个「实心三角 + 凹槽按钮盒」。悬停时切强调色，对应原型
        ``.dd-btn:hover{border-color:var(--accent)}``。
        """
        t = get_tokens()
        r = option.rect
        w = min(float(r.width()), 11.0)
        h = w * 0.62
        cx = float(r.center().x())
        cy = float(r.center().y()) + h * 0.1

        path = QPainterPath()
        path.moveTo(cx - w / 2, cy - h / 2)
        path.lineTo(cx, cy + h / 2)
        path.lineTo(cx + w / 2, cy - h / 2)

        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        pen = QPen(QColor(t.accent if hovered else t.text_disabled))
        pen.setWidthF(1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()
