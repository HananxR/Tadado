"""About dialog — WeChat-style minimal about page.

Layout (mirrors 微信 → 设置 → 关于微信):
    centred app icon + name + version + tagline,
    hairline menu rows (检查更新 / 下载渠道 / 交流反馈) with right chevrons,
    minimal changelog section, and a subtle close button.
"""

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

_GITHUB_REPO = "https://github.com/HananxR/Tadado"
_GITHUB_RELEASES = f"{_GITHUB_REPO}/releases"


class _MenuRow(QPushButton):
    """WeChat-style menu row: left title + right detail/chevron, hairline hover."""

    def __init__(self, title: str, detail: str = "›", parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("aboutMenuRow")
        t = get_tokens()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: 13px; color: {t.text_primary};")
        layout.addWidget(title_label)
        layout.addStretch()

        self._detail = QLabel(detail)
        self._detail.setStyleSheet(f"font-size: 12px; color: {t.text_secondary};")
        layout.addWidget(self._detail)

        self.setStyleSheet(
            f"QPushButton#aboutMenuRow {{"
            f"  border: none; background: transparent; text-align: left;"
            f"  border-bottom: 1px solid {t.border_primary};"
            f"}}"
            f"QPushButton#aboutMenuRow:hover {{ background: {t.bg_tertiary}; }}"
        )

    def set_detail(self, text: str) -> None:
        self._detail.setText(text)


class AboutDialog(QDialog):
    """App information — minimal WeChat-style about page."""

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
        self.resize(420, 560)
        self.setMinimumSize(360, 460)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = get_tokens()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Top bar: title + close (subtle ✕, WeChat-style) ──
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(16, 10, 10, 6)
        title_label = QLabel("关于 Tadado")
        title_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {t.text_primary};"
        )
        top_layout.addWidget(title_label)
        top_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: none; border-radius: 4px; background: transparent;"
            f"  color: {t.text_secondary}; font-size: 13px;"
            f"}}"
            f"QPushButton:hover {{ background: {t.bg_tertiary}; color: {t.text_primary}; }}"
        )
        close_btn.clicked.connect(self.reject)
        top_layout.addWidget(close_btn)
        outer.addWidget(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 8, 32, 20)
        layout.setSpacing(0)

        # ── Brand block (centred, generous whitespace) ──
        logo = QLabel()
        logo_path = self._find_icon("app_icon.svg")
        pix = QPixmap(logo_path) if logo_path else QPixmap()
        if not pix.isNull():
            pix = pix.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(pix)
        else:
            logo.setText("✦")
            logo.setStyleSheet(f"font-size: 44px; color: {t.accent};")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(14)

        name = QLabel("Tadado")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {t.text_primary};")
        layout.addWidget(name)
        layout.addSpacing(4)

        ver = QLabel(f"Version {get_version_display()}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"font-size: 12px; color: {t.text_secondary};")
        layout.addWidget(ver)
        layout.addSpacing(2)

        tagline = QLabel("Less Noise, More Done")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"font-size: 12px; color: {t.text_secondary};")
        layout.addWidget(tagline)
        layout.addSpacing(24)

        # ── Menu rows ──
        self._check_row = _MenuRow("检查更新", "检查中" if self._update_checker is None else "›")
        self._check_row.clicked.connect(self._on_check_updates)
        layout.addWidget(self._check_row)

        self._github_row = _MenuRow("下载渠道 · GitHub Releases")
        self._github_row.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_GITHUB_RELEASES))
        )
        layout.addWidget(self._github_row)

        self._aliyun_row = _MenuRow("下载渠道 · 阿里云盘")
        self._aliyun_row.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(ALIYUN_DRIVE_URL))
        )
        layout.addWidget(self._aliyun_row)

        email_row = _MenuRow("意见反馈 · 邮箱", "hanxy8413@gmail.com")
        email_row.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("mailto:hanxy8413@gmail.com"))
        )
        layout.addWidget(email_row)

        wechat_row = _MenuRow("微信公众号", "Pyvan")
        wechat_row.set_detail("Pyvan")
        layout.addWidget(wechat_row)

        repo_row = _MenuRow("GitHub 仓库")
        repo_row.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_GITHUB_REPO))
        )
        layout.addWidget(repo_row)

        layout.addSpacing(20)

        # ── Changelog (minimal, no card) ──
        highlights = get_release_highlights()
        if highlights:
            _CAT_ICONS = {"新增": "✨", "优化": "🔧", "修复": "🐛"}
            hl_parts = [
                f'<p style="margin:0 0 6px 0;font-size:12px;font-weight:700;'
                f'color:{t.text_primary};">版本更新记录</p>'
            ]
            for cat, items in highlights.items():
                if not items:
                    continue
                icon = _CAT_ICONS.get(cat, "•")
                hl_parts.append(
                    f'<p style="margin:8px 0 2px 0;font-size:11px;font-weight:600;'
                    f'color:{t.text_primary};">{icon} {cat}</p>'
                )
                for item in items:
                    safe = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    safe = safe.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
                    hl_parts.append(
                        f'<p style="margin:2px 0 2px 8px;font-size:11px;'
                        f'line-height:1.7;color:{t.text_secondary};">· {safe}</p>'
                    )
            hl_label = QLabel("".join(hl_parts))
            hl_label.setTextFormat(Qt.TextFormat.RichText)
        else:
            hl_label = QLabel(
                f'<p style="margin:6px 0 2px 0;font-size:11px;color:{t.text_secondary};">'
                f'暂无当前版本更新记录</p>'
            )
            hl_label.setTextFormat(Qt.TextFormat.RichText)
        hl_label.setWordWrap(True)
        layout.addWidget(hl_label)

        layout.addStretch()

        # ── Copyright ──
        copyright_label = QLabel("Copyright © 2026 HananxR · MIT License")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_label.setStyleSheet(f"font-size: 10px; color: {t.text_secondary};")
        layout.addWidget(copyright_label)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    # ── Update check slots ────────────────────────────────────────

    def _on_check_updates(self) -> None:
        if self._update_checker is None:
            self._check_row.set_detail("不可用")
            return

        self._check_row.setEnabled(False)
        self._check_row.set_detail("检查中…")
        self._update_checker.check_finished.connect(
            self._on_check_finished, type=Qt.ConnectionType.SingleShotConnection
        )
        self._update_checker.check_error.connect(
            self._on_check_error, type=Qt.ConnectionType.SingleShotConnection
        )
        self._update_checker.check_for_updates()

    def _on_check_finished(self, update_info: dict | None) -> None:
        t = get_tokens()
        self._check_row.setEnabled(True)
        if update_info is None:
            self._check_row.set_detail(f"✓ 已是最新版本")
            self._check_row._detail.setStyleSheet(
                f"font-size: 12px; color: {t.success};"
            )
        else:
            self._update_info = update_info
            latest = update_info.get("latest_version", "")
            self._check_row.set_detail(f"发现新版本 {latest}")
            self._check_row._detail.setStyleSheet(
                f"font-size: 12px; color: {t.accent}; font-weight: 600;"
            )

    def _on_check_error(self, message: str) -> None:
        t = get_tokens()
        self._check_row.setEnabled(True)
        self._check_row.set_detail(message)
        self._check_row._detail.setStyleSheet(
            f"font-size: 12px; color: {t.danger};"
        )

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
