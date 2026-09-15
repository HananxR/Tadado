"""SideDrawer —— 通用右侧滑入抽屉基类（对齐原型 ``.drawer``）。

原型里「维护抽屉」与「设置面板」共用同一个 ``.drawer`` 外壳，只有宽度不同
（392px / 420px）：

.. code-block:: css

    .drawer{position:fixed;top:var(--bar-h);right:0;bottom:0;width:392px;
            transform:translateX(105%);
            transition:transform .3s cubic-bezier(.22,1,.36,1);
            box-shadow:-14px 0 44px -16px rgba(0,0,0,.35);
            border-left:1px solid var(--border);background:var(--surface);
            display:flex;flex-direction:column}
    .drawer.open{transform:none}
    .dr-h{display:flex;align-items:center;gap:10px;padding:16px 18px 12px;
          border-bottom:1px solid var(--border);flex-wrap:wrap}
    .dr-h .t{font:700 15px var(--font);flex:1;min-width:0}
    .dr-b{padding:14px 18px;overflow-y:auto;flex:1}
    .dr-f{padding:12px 18px;border-top:1px solid var(--border);
          display:flex;gap:8px;justify-content:flex-end}

实现要点：
* 抽屉是父部件的**子部件**（不是顶层窗口），因此定位靠 ``pos`` 动画而非
  ``QPropertyAnimation`` 作用于窗口几何；父窗口缩放时要重新贴右。
* 原型那圈 ``box-shadow`` 在 Qt 里没有等价物，用 ``QGraphicsDropShadowEffect``
  会让整棵子树每帧重绘（动画期掉帧很严重）。这里改为在抽屉左侧预留
  :data:`SHADOW_PAD` 宽的透明槽位，用 ``QLinearGradient`` 直接画出投影——
  开销与普通绘制一致，视觉上与原型一致。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...utils.design_tokens import expand_qss, get_tokens, is_dark, surface_color
from ...utils.icon_loader import load_icon
from ...utils.theme_registry import register_theme_aware

#: 左侧投影槽位宽度（原型 ``box-shadow`` 的 blur 44px − spread 16px ≈ 28px）
SHADOW_PAD = 24
#: 滑入 / 滑出时长（原型 ``transition:.3s``）
ANIM_MS = 260
#: 默认抽屉宽度（原型 ``.drawer`` = 392px；设置面板覆写为 420px）
DRAWER_WIDTH = 392


class SideDrawer(QWidget):
    """右侧滑入抽屉外壳：头部（标题 + 槽位 + 关闭）+ 可滚动主体 + 可选底栏。"""

    #: 抽屉完全收起后发出
    closed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        width: int = DRAWER_WIDTH,
        title: str = "",
        animate: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sideDrawer")
        self._width = width
        self._animate = animate
        self._showing = False
        self._anim: QPropertyAnimation | None = None
        self._esc_filter = False

        # 真实宽度 = 面板宽度 + 左侧投影槽位；面板贴住父窗口右缘
        self.setFixedWidth(width + SHADOW_PAD)
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(SHADOW_PAD, 0, 0, 0)
        root.setSpacing(0)

        self._panel = QFrame()
        self._panel.setObjectName("drawerPanel")
        root.addWidget(self._panel)

        panel = QVBoxLayout(self._panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(0)

        # ── 头部（.dr-h）──
        self._head = QWidget()
        self._head.setObjectName("drawerHead")
        self._head_row = QHBoxLayout(self._head)
        self._head_row.setContentsMargins(18, 14, 14, 12)
        self._head_row.setSpacing(10)
        self._title = QLabel(title)
        self._title.setObjectName("drawerTitle")
        self._head_row.addWidget(self._title, 1)

        self._close_btn = QPushButton()
        self._close_btn.setObjectName("iconBtn")
        self._close_btn.setIcon(load_icon("window_close"))
        self._close_btn.setIconSize(QSize(13, 13))
        self._close_btn.setFixedSize(26, 26)
        self._close_btn.setFlat(True)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("关闭 (Esc)")
        self._close_btn.clicked.connect(self.close_drawer)
        self._head_row.addWidget(self._close_btn, 0)
        panel.addWidget(self._head)

        # ── 主体（.dr-b）──
        self._scroll = QScrollArea()
        self._scroll.setObjectName("drawerScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.body = QWidget()
        self.body.setObjectName("drawerBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 14, 18, 16)
        self.body_layout.setSpacing(0)
        self._scroll.setWidget(self.body)
        panel.addWidget(self._scroll, 1)

        self._footer: QWidget | None = None

        # 只应用外壳样式：子类的 refresh_theme 覆写此时字段还未就绪
        self._apply_shell_theme()
        register_theme_aware(self)

        if animate:
            self._anim = QPropertyAnimation(self, b"pos", self)
            self._anim.setDuration(ANIM_MS)
            self._anim.setEasingCurve(QEasingCurve.Type.OutQuint)

    # ------------------------------------------------------------------
    # 装配 API（子类用）
    # ------------------------------------------------------------------

    def add_header_widget(self, widget: QWidget) -> None:
        """把部件插到头部标题之后、关闭按钮之前（原型 ``.dr-h`` 的中间槽）。"""
        self._head_row.insertWidget(self._head_row.count() - 1, widget)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_footer(self, widget: QWidget) -> None:
        """设置底栏（原型 ``.dr-f``）；只调用一次。"""
        if self._footer is not None:
            raise RuntimeError("SideDrawer footer 已存在")
        self._footer = widget
        self._panel.layout().addWidget(widget)

    # ------------------------------------------------------------------
    # 开合
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._showing

    def open_drawer(self) -> None:
        """滑入；已打开时只重新贴右并置顶。"""
        if self._showing:
            self._reposition()
            self.raise_()
            return
        self.on_before_open()
        self._slide(in_=True)

    def close_drawer(self) -> None:
        """滑出，动画结束后 ``hide()`` 并发 :attr:`closed`。"""
        if not self._showing:
            return
        self._slide(in_=False)

    def toggle_drawer(self) -> None:
        self.close_drawer() if self._showing else self.open_drawer()

    def on_before_open(self) -> None:
        """子类钩子：每次打开前刷新内容（默认无操作）。"""

    # ------------------------------------------------------------------
    # 动画 / 定位
    # ------------------------------------------------------------------

    def _slide(self, *, in_: bool) -> None:
        parent = self.parentWidget()
        if parent is None:
            self.setVisible(in_)
            self._showing = in_
            self._sync_esc_filter()
            if not in_:
                self.closed.emit()
            return

        height = parent.height()
        end_x = parent.width() - self.width() if in_ else parent.width()
        if in_:
            self.setGeometry(parent.width(), 0, self.width(), height)
            self.show()
            self.raise_()
            self._showing = True
            self._sync_esc_filter()

        if self._anim is None:
            self.setGeometry(end_x, 0, self.width(), height)
            if not in_:
                self._finish_close()
            return

        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(QPoint(end_x, 0))
        self._anim.start()

    def reposition(self) -> None:
        """重新贴住父窗口右缘（父窗口缩放后由外部调用）。"""
        self._reposition()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = parent.width() - self.width() if self._showing else parent.width()
        if self.x() != x or self.height() != parent.height():
            self.setGeometry(x, 0, self.width(), parent.height())

    def _finish_close(self) -> None:
        self._showing = False
        self._sync_esc_filter()
        self.hide()
        self.closed.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition()

    # ------------------------------------------------------------------
    # Esc 关闭
    # ------------------------------------------------------------------

    def _sync_esc_filter(self) -> None:
        """窗口级 Esc 拦截：抽屉没有焦点时也要能关。"""
        window = self.window()
        if self._showing and not self._esc_filter:
            window.installEventFilter(self)
            self._esc_filter = True
        elif not self._showing and self._esc_filter:
            window.removeEventFilter(self)
            self._esc_filter = False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if (
            self._esc_filter
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self.close_drawer()
            return True
        return super().eventFilter(obj, event)

    def hideEvent(self, event) -> None:  # noqa: N802
        # 外部（父窗口销毁 / 直接 hide）收起时同步状态，避免 Esc 过滤器残留
        if self._esc_filter:
            self.window().removeEventFilter(self)
            self._esc_filter = False
        was_showing = self._showing
        self._showing = False
        super().hideEvent(event)
        if was_showing:
            self.closed.emit()

    # ------------------------------------------------------------------
    # 绘制 / 主题
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        """在左侧槽位画出投影渐变（等价原型 ``box-shadow``）。

        与 :func:`~src.utils.design_tokens.apply_elevation` 第 3 档**同源**：
        色相与浓度都取自 ``ELEVATION``，保证抽屉与弹层的浮起感一致。
        这里仍走自绘而非 ``QGraphicsDropShadowEffect``——抽屉滑入时会整棵
        子树逐帧重绘，特效版实测掉帧。
        """
        from ...utils.design_tokens import elevation_params

        painter = QPainter(self)
        base = elevation_params(3)["color"]
        near = QColor(base)
        near.setAlpha(base.alpha() // 3)
        far = QColor(base)
        far.setAlpha(0)
        grad = QLinearGradient(0.0, 0.0, float(SHADOW_PAD), 0.0)
        grad.setColorAt(0.0, far)
        grad.setColorAt(0.55, near)
        grad.setColorAt(1.0, base)
        painter.fillRect(0, 0, SHADOW_PAD, self.height(), grad)
        painter.end()

    def refresh_theme(self) -> None:
        """重放外壳取色；子类覆写时应先调用 ``super().refresh_theme()``。"""
        self._apply_shell_theme()

    def _apply_shell_theme(self) -> None:
        """面板 / 头部 / 标题 / 关闭按钮的取色（子类构造期也会走到）。"""
        t = get_tokens()
        # ``surface`` 是派生色（DesignTokens 上没有该字段），故用 surface_color()。
        # 面板底色必须走 ``--surface``（#fbfaf6），**不是** surface_raised
        # （#ffffff）。原型 .drawer 就是用 var(--surface)：抽屉是一张大面板，
        # 用纯白会比页面（--bg #f4f3ef）亮出整整 11 个色阶，看上去像贴了块
        # 白板；#fbfaf6 只亮 5 个色阶，才有"暖纸上浮起一层"的观感。
        self._panel.setStyleSheet(
            f"QFrame#drawerPanel {{"
            f" background: {surface_color(is_dark())};"
            f" border-left: 1px solid {t.border_primary}; }}"
        )
        self._head.setStyleSheet(
            f"QWidget#drawerHead {{"
            f" background: {surface_color(is_dark())};"
            f" border-bottom: 1px solid {t.border_primary}; }}"
        )
        # #drawerTitle 的字号/字重已由 base.qss 的字阶统一给出，此处不再重复。
        # 关闭按钮的 hover 走 {{hover}}（原型的 accent 淡染）——此前用
        # bg_tertiary（凹槽灰），视觉上像"已按下"而不是"悬停"。
        self._close_btn.setStyleSheet(
            expand_qss(
                "QPushButton#iconBtn { border: none; border-radius: 7px;"
                " background: transparent; padding: 0px; }"
                "QPushButton#iconBtn:hover { background: {{hover}}; }"
            )
        )
        self._scroll.setStyleSheet(
            "QScrollArea#drawerScroll { background: transparent; border: none; }"
            "QWidget#drawerBody { background: transparent; }"
        )
