"""About dialog — version info, update check, download channels, and contact."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...services.update_checker import ALIYUN_DRIVE_URL, UpdateChecker
from ...utils.design_tokens import get_surface_color, get_tokens, is_dark
from ...utils.win32_theme import is_dark_mode_supported, set_window_dark_mode
from ...version import get_release_highlights, get_version_display

_FEATURES = [
    ("📝 Markdown 任务管理", "语法创建，优先级、截止时间、全文搜索"),
    ("📊 活动分析", "日历热力图、活动时间线、工作报告导出"),
    ("🔧 批量操作", "全选、右键批量变更状态、延后、中止、删除"),
    ("🏷 标签管理", "重命名、合并，全局自动同步"),
    ("🔒 分区管理", "多分区隔离，密码保护，自动锁定"),
    ("⏰ 智能提醒", "到期通知、免打扰安静时段、托盘弹窗"),
]

_GITHUB_REPO = "https://github.com/HananxR/Tadado"
_GITHUB_RELEASES = f"{_GITHUB_REPO}/releases"


class AboutDialog(QDialog):
    """App information, version, update check, download channels, and contact."""

    @staticmethod
    def _build_channels_html(github_star: bool = False, aliyun_star: bool = False) -> str:
        """Build download channels HTML with optional ⭐ recommendation marker."""
        gh = "⭐ 推荐 " if github_star else ""
        ay = "⭐ 推荐 " if aliyun_star else ""
        return (
            '<p style="margin:6px 0 2px 0;font-size:11px;">下载渠道</p>'
            '<p style="margin:2px 0 2px 12px;font-size:11px;">'
            f'🌐 <a href="{_GITHUB_RELEASES}" style="color: palette(link);">{gh}GitHub Releases</a>'
            '</p>'
            '<p style="margin:2px 0 2px 12px;font-size:11px;">'
            f'☁️ <a href="{ALIYUN_DRIVE_URL}" style="color: palette(link);">{ay}阿里云盘（仅提供安装版）</a>'
            '</p>'
        )

    def __init__(
        self,
        parent: QWidget | None = None,
        update_checker: UpdateChecker | None = None,
    ) -> None:
        super().__init__(parent)
        self._update_checker = update_checker
        self._update_info: dict | None = None

        self.setWindowTitle("关于 Tadado")
        self.setObjectName("aboutDialog")
        self.resize(440, 560)
        self.setMinimumSize(380, 480)

        t = get_tokens()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)

        # ── Logo ──
        logo = QLabel()
        logo_path = self._find_icon("app_icon.svg")
        pix = QPixmap(logo_path) if logo_path else QPixmap()
        if not pix.isNull():
            pix = pix.scaled(
                72, 72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(pix)
        else:
            logo.setText("✦")
            logo.setStyleSheet("font-size: 52px; color: #6366F1;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(14)

        # ── Name + version ──
        name = QLabel("Tadado")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(name)
        layout.addSpacing(2)

        ver = QLabel("Less noise. More done.")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("font-size: 12px; color: palette(mid);")
        layout.addWidget(ver)
        layout.addSpacing(12)

        # ── Separator ──
        layout.addWidget(_h_line())
        layout.addSpacing(14)

        # ── Feature list ──
        for title, desc in _FEATURES:
            row = QLabel(
                f'<b style="font-size:12px;">{title}</b>'
                f'<span style="font-size:11px; color:palette(mid);">: {desc}</span>'
            )
            row.setWordWrap(True)
            layout.addWidget(row)
            layout.addSpacing(6)

        layout.addSpacing(6)

        # ── Separator ──
        layout.addWidget(_h_line())
        layout.addSpacing(14)

        # ══════════════════════════════════════════════════════════════
        # 版本与更新（含升级日志）
        # ══════════════════════════════════════════════════════════════
        section_label = QLabel("版本与更新")
        section_label.setStyleSheet("font-size: 12px; font-weight: 700;")
        layout.addWidget(section_label)
        layout.addSpacing(4)

        # Row: version + check button
        version_row = QWidget()
        version_row_layout = QHBoxLayout(version_row)
        version_row_layout.setContentsMargins(0, 0, 0, 0)
        version_row_layout.setSpacing(8)

        self._version_label = QLabel(f"当前版本: {get_version_display()}")
        self._version_label.setStyleSheet("font-size: 11px; color: palette(mid);")
        version_row_layout.addWidget(self._version_label, 1)

        self._check_btn = QPushButton("检查更新")
        self._check_btn.setFixedHeight(26)
        self._check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_btn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size: 11px; padding: 2px 12px;"
            f"  border: 1px solid {t.border_primary};"
            f"  border-radius: 4px;"
            f"  background: {t.bg_secondary};"
            f"  color: {t.text_primary};"
            f"}}"
            f"QPushButton:hover {{"
            f"  border-color: {t.accent};"
            f"  color: {t.accent};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  color: {t.text_disabled};"
            f"}}"
        )
        self._check_btn.clicked.connect(self._on_check_updates)
        version_row_layout.addWidget(self._check_btn)
        layout.addWidget(version_row)

        # Upgrade highlights (below version row)
        highlights = get_release_highlights()
        if highlights:
            hl_parts = ['<p style="margin:6px 0 2px 0;font-size:11px;">升级内容</p>']
            for item in highlights:
                safe = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                hl_parts.append(
                    f'<p style="margin:2px 0 2px 12px;font-size:11px;">· {safe}</p>'
                )
            hl_label = QLabel("".join(hl_parts))
            hl_label.setWordWrap(True)
            hl_label.setTextFormat(Qt.TextFormat.RichText)
            hl_label.setStyleSheet(f"QLabel {{ color: {t.text_primary}; }}")
            layout.addWidget(hl_label)

        # Download channels (below highlights)
        self._channels_label = QLabel(self._build_channels_html())
        self._channels_label.setOpenExternalLinks(True)
        self._channels_label.setStyleSheet("font-size: 11px;")
        self._channels_label.setWordWrap(True)
        layout.addWidget(self._channels_label)

        # Result text (below channels)
        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)

        layout.addSpacing(14)

        # ── Separator ──
        layout.addWidget(_h_line())
        layout.addSpacing(14)

        # ══════════════════════════════════════════════════════════════
        # 交流方式
        # ══════════════════════════════════════════════════════════════
        contact_title = QLabel("交流方式")
        contact_title.setStyleSheet("font-size: 12px; font-weight: 700;")
        layout.addWidget(contact_title)
        layout.addSpacing(4)

        email = QLabel(
            f'📧 <a href="mailto:hanxy8413@gmail.com" style="color: palette(link);">'
            f'hanxy8413@gmail.com</a>'
        )
        email.setOpenExternalLinks(True)
        email.setStyleSheet("font-size: 11px;")
        layout.addWidget(email)

        wechat = QLabel("💬 微信公众号：Pyvan")
        wechat.setStyleSheet("font-size: 11px;")
        layout.addWidget(wechat)

        repo = QLabel(
            f'🌐 <a href="{_GITHUB_REPO}" style="color: palette(link);">'
            f'github.com/HananxR/Tadado</a>'
        )
        repo.setOpenExternalLinks(True)
        repo.setStyleSheet("font-size: 11px;")
        layout.addWidget(repo)

        layout.addSpacing(12)

        # ── Footer ──
        layout.addWidget(_h_line())
        layout.addSpacing(14)

        foot = QLabel("MIT License  ·  HananxR")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setStyleSheet("font-size: 11px; color: palette(mid);")
        layout.addWidget(foot)

        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        close_wrapper = QHBoxLayout()
        close_wrapper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        close_wrapper.addWidget(close_btn)
        outer.addLayout(close_wrapper)

    # ── Update check slots ────────────────────────────────────────

    def _on_check_updates(self) -> None:
        if self._update_checker is None:
            self._result_label.setText("⚠ 更新检测不可用")
            self._result_label.setStyleSheet(
                f"font-size: 11px; padding-top: 4px;"
                f"color: {get_tokens().text_secondary};"
            )
            self._result_label.setVisible(True)
            return

        self._check_btn.setEnabled(False)
        self._check_btn.setText("检查中...")
        # Reset version label to default
        self._version_label.setText(f"当前版本: {get_version_display()}")
        self._version_label.setStyleSheet("font-size: 11px; color: palette(mid);")
        self._result_label.setVisible(False)
        # Reset channels to default (remove any ⭐ from previous check)
        self._channels_label.setText(self._build_channels_html())

        self._update_checker.check_finished.connect(
            self._on_check_finished, type=Qt.ConnectionType.SingleShotConnection
        )
        self._update_checker.check_error.connect(
            self._on_check_error, type=Qt.ConnectionType.SingleShotConnection
        )
        self._update_checker.check_for_updates()

    def _on_check_finished(self, update_info: dict | None) -> None:
        t = get_tokens()
        self._check_btn.setEnabled(True)
        self._check_btn.setText("检查更新")

        if update_info is None:
            self._version_label.setText(f"当前版本: {get_version_display()}")
            self._version_label.setStyleSheet("font-size: 11px; color: palette(mid);")
        else:
            self._update_info = update_info
            latest = update_info.get("latest_version", "")
            source = update_info.get("source", "github")
            self._version_label.setText(
                f"当前版本: {get_version_display()}  →  {latest}"
            )
            self._version_label.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: {t.accent};"
            )
            # Mark the recommended channel with ⭐
            if source == "aliyunpan":
                self._channels_label.setText(
                    self._build_channels_html(aliyun_star=True)
                )
            else:
                self._channels_label.setText(
                    self._build_channels_html(github_star=True)
                )

    def _on_check_error(self, message: str) -> None:
        """Shown only for non-timeout errors (e.g. GitHub rate limit)."""
        t = get_tokens()
        self._check_btn.setEnabled(True)
        self._check_btn.setText("检查更新")
        self._result_label.setText(f"⚡ {message}")
        self._result_label.setStyleSheet(
            f"font-size: 11px; padding-top: 4px; color: {t.danger};"
        )
        self._result_label.setVisible(True)

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _find_icon(name: str) -> str | None:
        import sys
        from pathlib import Path

        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        p = base / "resources" / "icons" / name
        return str(p) if p.exists() else None

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if is_dark_mode_supported() and is_dark():
            set_window_dark_mode(self, True, caption_color=get_surface_color())


# ── Private helpers ──────────────────────────────────────────────────


def _h_line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("QFrame { color: palette(mid); }")
    line.setFixedHeight(1)
    return line
