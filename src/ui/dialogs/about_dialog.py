"""About dialog — version info, update check, download channels, and contact."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...services.changelog_parser import format_changelog_html, get_version_changelog
from ...services.update_checker import ALIYUN_DRIVE_URL, UpdateChecker
from ...utils.design_tokens import get_surface_color, get_tokens, is_dark
from ...utils.win32_theme import is_dark_mode_supported, set_window_dark_mode
from ...version import __version__, get_version_display

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

    _CHANNELS_GITHUB = "🌐 GitHub Releases"
    _CHANNELS_ALIYUN = "☁️ 阿里云盘（仅提供安装版）"
    _DEFAULT_CHANNELS = (
        f'<a href="{_GITHUB_RELEASES}" style="color: palette(link);">'
        f'{_CHANNELS_GITHUB}</a><br/>'
        f'<a href="{ALIYUN_DRIVE_URL}" style="color: palette(link);">'
        f'{_CHANNELS_ALIYUN}</a>'
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

        ver = QLabel(f"{get_version_display()}  ·  Less noise. More done.")
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
                f'<span style="font-size:11px; color:palette(mid);"> &nbsp;—&nbsp; {desc}</span>'
            )
            row.setWordWrap(True)
            layout.addWidget(row)
            layout.addSpacing(6)

        layout.addSpacing(6)

        # ── Separator ──
        layout.addWidget(_h_line())
        layout.addSpacing(14)

        # ══════════════════════════════════════════════════════════════
        # 更新日志
        # ══════════════════════════════════════════════════════════════
        entry = get_version_changelog(__version__)
        if entry:
            cl_html = format_changelog_html(entry)
            self._changelog_label = QLabel(cl_html)
            self._changelog_label.setWordWrap(True)
            self._changelog_label.setTextFormat(Qt.TextFormat.RichText)
            self._changelog_label.setStyleSheet(
                f"QLabel {{ padding: 2px 0; color: {t.text_primary}; }}"
            )
            layout.addWidget(self._changelog_label)
            layout.addSpacing(12)
            layout.addWidget(_h_line())
            layout.addSpacing(14)

        # ══════════════════════════════════════════════════════════════
        # 版本与更新
        # ══════════════════════════════════════════════════════════════
        section_label = QLabel("版本与更新")
        section_label.setStyleSheet("font-size: 12px; font-weight: 700;")
        layout.addWidget(section_label)
        layout.addSpacing(6)

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

        # Result text (below version row)
        self._result_label = QLabel("")
        self._result_label.setWordWrap(True)
        self._result_label.setVisible(False)
        layout.addWidget(self._result_label)

        layout.addSpacing(10)

        # Download channels (dynamic — ⭐ added when update found)
        self._channels_label = QLabel(self._DEFAULT_CHANNELS)
        self._channels_label.setOpenExternalLinks(True)
        self._channels_label.setStyleSheet("font-size: 11px;")
        self._channels_label.setWordWrap(True)
        layout.addWidget(self._channels_label)

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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.setCenterButtons(True)
        outer.addWidget(buttons)

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
        self._result_label.setVisible(False)
        # Reset channels to default (remove any ⭐ from previous check)
        self._channels_label.setText(self._DEFAULT_CHANNELS)

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
            self._result_label.setText("✓ 已是最新版本")
            self._result_label.setStyleSheet(
                f"font-size: 11px; padding-top: 4px; color: {t.success};"
            )
            self._result_label.setVisible(True)
        else:
            self._update_info = update_info
            latest = update_info.get("latest_version", "")
            source = update_info.get("source", "github")
            self._result_label.setText(
                f"🆕 发现新版本 {latest}"
            )
            self._result_label.setStyleSheet(
                f"font-size: 11px; padding-top: 4px;"
                f"font-weight: 600; color: {t.accent};"
            )
            self._result_label.setVisible(True)
            # Mark the recommended channel with ⭐
            if source == "aliyunpan":
                rec = "⭐ 推荐 ☁️ 阿里云盘（仅提供安装版）"
                other = "🌐 GitHub Releases"
            else:
                rec = "⭐ 推荐 🌐 GitHub Releases"
                other = "☁️ 阿里云盘（仅提供安装版）"
            self._channels_label.setText(
                f'<a href="{_GITHUB_RELEASES if source == "github" else ALIYUN_DRIVE_URL}"'
                f' style="color: palette(link);">{rec}</a><br/>'
                f'<span style="color: palette(mid); font-size:10px;">{other}</span>'
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
