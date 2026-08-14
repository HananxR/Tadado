"""About dialog — WeChat-style about page + dedicated version-history page.

Main page (fixed height, fully controlled layout):
    brand block (icon / name / version / tagline) + hairline menu rows.
Version history lives in its own scrollable dialog, opened from a menu row
— the main page never grows unpredictably.
"""

from __future__ import annotations

import re
from datetime import datetime

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

_CAT_LABELS = {"Added": "新增", "Changed": "优化", "Fixed": "修复"}
_CAT_ICONS = {"新增": "✨", "优化": "🔧", "修复": "🐛"}


def _md_to_html(text: str, t) -> str:
    """CHANGELOG Markdown 片段 → 富文本（加粗/行内代码/链接）."""
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 兼容历史条目里写死的 <code> 标签
    safe = safe.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        rf'<a href="\2" style="color:{t.accent}; text-decoration:none;">\1</a>',
        safe,
    )
    return safe


def _parse_changelog_md() -> list[dict]:
    """Parse CHANGELOG.md into [{version, date, categories:[(label, [items])]}].

    Returns [] when the file is unavailable (frozen builds) — callers fall
    back to the current version's release highlights.
    """
    import sys
    from pathlib import Path

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    path = base / "CHANGELOG.md"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    versions: list[dict] = []
    current: dict | None = None
    current_cat: str | None = None
    for line in text.splitlines():
        m = re.match(r"^##\s+\[([\d.]+)\]\s*[—\-]\s*(.+)$", line.strip())
        if m:
            current = {"version": m.group(1), "date": m.group(2).strip(),
                       "categories": []}
            versions.append(current)
            current_cat = None
            continue
        m = re.match(r"^###\s+(Added|Changed|Fixed)", line.strip())
        if m and current is not None:
            current_cat = _CAT_LABELS[m.group(1)]
            current["categories"].append((current_cat, []))
            continue
        m = re.match(r"^[-*]\s+(.+)", line.strip())
        if m and current is not None and current_cat is not None:
            item = m.group(1).strip().lstrip("*").strip()
            if item:
                current["categories"][-1][1].append(item)
    return versions


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


def _close_button(clicked) -> QPushButton:
    t = get_tokens()
    btn = QPushButton("✕")
    btn.setFixedSize(28, 28)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(
        f"QPushButton {{"
        f"  border: none; border-radius: 4px; background: transparent;"
        f"  color: {t.text_secondary}; font-size: 13px;"
        f"}}"
        f"QPushButton:hover {{ background: {t.bg_tertiary}; color: {t.text_primary}; }}"
    )
    btn.clicked.connect(clicked)
    return btn


class _HeaderBar(QWidget):
    """Title + ✕ close — shared by both pages."""

    def __init__(self, title: str, close_callback, parent=None) -> None:
        super().__init__(parent)
        t = get_tokens()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 10, 6)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {t.text_primary};"
        )
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(_close_button(close_callback))


class ChannelsDialog(QDialog):
    """下载渠道子页 — 「下载渠道」菜单行的下级页面."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("下载渠道")
        self.setObjectName("channelsDialog")
        self.setFixedSize(380, 200)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_HeaderBar("下载渠道", self.reject))

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 8, 24, 16)
        layout.setSpacing(0)

        github_row = _MenuRow("GitHub Releases")
        github_row.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_GITHUB_RELEASES))
        )
        layout.addWidget(github_row)

        aliyun_row = _MenuRow("阿里云盘（仅 .exe）")
        aliyun_row.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(ALIYUN_DRIVE_URL))
        )
        layout.addWidget(aliyun_row)

        layout.addSpacing(14)

        t = get_tokens()
        note = QLabel("两个渠道发布的安装包内容一致，任选其一即可。")
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size: 11px; color: {t.text_secondary};")
        layout.addWidget(note)
        layout.addStretch()

        outer.addWidget(content, 1)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if is_dark_mode_supported() and is_dark():
            set_window_dark_mode(self, True, caption_color=get_surface_color())


class VersionHistoryDialog(QDialog):
    """独立滚动页：全版本更新记录（CHANGELOG.md 解析，缺省回退当前版本 highlights）."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("版本更新记录")
        self.setObjectName("versionHistoryDialog")
        self.resize(460, 600)
        self.setMinimumSize(380, 480)

        t = get_tokens()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_HeaderBar("版本更新记录", self.reject))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 8, 28, 24)
        layout.setSpacing(0)

        versions = _parse_changelog_md()
        if not versions:
            highlights = get_release_highlights()
            versions = [{
                "version": get_version_display(),
                "date": "",
                "categories": [(cat, list(items)) for cat, items in highlights.items() if items],
            }]

        cat_colors = {"新增": t.success, "优化": t.warning, "修复": t.danger}

        for vi, ver in enumerate(versions):
            if vi:
                layout.addSpacing(16)
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet(f"QFrame {{ color: {t.border_primary}; }}")
                sep.setFixedHeight(1)
                layout.addWidget(sep)
                layout.addSpacing(14)

            # 版本标题行：版本号 + 日期右对齐，正式版式
            header_row = QWidget()
            header_layout = QHBoxLayout(header_row)
            header_layout.setContentsMargins(0, 0, 0, 0)
            version_label = QLabel(f"v{ver['version']}")
            version_label.setStyleSheet(
                f"font-size: 15px; font-weight: 700; color: {t.text_primary};"
            )
            header_layout.addWidget(version_label)
            header_layout.addStretch()
            if ver.get("date"):
                date_label = QLabel(ver["date"])
                date_label.setStyleSheet(
                    f"font-size: 11px; color: {t.text_secondary};"
                )
                header_layout.addWidget(date_label)
            layout.addWidget(header_row)
            layout.addSpacing(8)

            for cat, items in ver["categories"]:
                if not items:
                    continue
                color = cat_colors.get(cat, t.text_primary)
                icon = _CAT_ICONS.get(cat, "•")
                cat_label = QLabel(
                    f'<span style="color:{color};">{icon} {cat}</span>'
                )
                cat_label.setStyleSheet(
                    f"font-size: 11px; font-weight: 700;"
                )
                layout.addWidget(cat_label)
                layout.addSpacing(2)
                for item in items:
                    entry = QLabel(f"· {_md_to_html(item, t)}")
                    entry.setWordWrap(True)
                    entry.setTextFormat(Qt.TextFormat.RichText)
                    entry.setOpenExternalLinks(True)
                    entry.setStyleSheet(
                        f"font-size: 12px; color: {t.text_secondary};"
                        f" padding-left: 12px;"
                    )
                    layout.addWidget(entry)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if is_dark_mode_supported() and is_dark():
            set_window_dark_mode(self, True, caption_color=get_surface_color())


class AboutDialog(QDialog):
    """App information — WeChat-style fixed-height about page."""

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
        self.setFixedSize(420, 540)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = get_tokens()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_HeaderBar("关于 Tadado", self.reject))

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 8, 32, 20)
        layout.setSpacing(0)

        # ── Brand block ──
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
        layout.addSpacing(12)

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
        layout.addSpacing(22)

        # ── Menu rows（分组：服务 / 下载 / 反馈） ──
        self._check_row = _MenuRow("检查更新")
        self._check_row.clicked.connect(self._on_check_updates)
        layout.addWidget(self._check_row)

        history_row = _MenuRow("版本更新记录")
        history_row.clicked.connect(self._open_history)
        layout.addWidget(history_row)

        layout.addSpacing(14)

        channels_row = _MenuRow("下载渠道")
        channels_row.clicked.connect(self._open_channels)
        layout.addWidget(channels_row)

        layout.addSpacing(14)

        email_row = _MenuRow("意见反馈", "hanxy8413@gmail.com")
        email_row.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("mailto:hanxy8413@gmail.com"))
        )
        layout.addWidget(email_row)

        wechat_row = _MenuRow("微信公众号", "Pyvan")
        layout.addWidget(wechat_row)

        layout.addStretch()

        # ── Copyright（GitHub 以超链接呈现） ──
        copyright_label = QLabel(
            f'Copyright © {datetime.now().year} HananxR · MIT License · '
            f'<a href="{_GITHUB_REPO}" style="color:{t.accent}; text-decoration:none;">GitHub</a>'
        )
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setTextFormat(Qt.TextFormat.RichText)
        copyright_label.setStyleSheet(
            f"font-size: 10px; color: {t.text_secondary};"
        )
        layout.addWidget(copyright_label)

        outer.addWidget(content, 1)

    def _open_history(self) -> None:
        VersionHistoryDialog(self).exec()

    def _open_channels(self) -> None:
        ChannelsDialog(self).exec()

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
            self._check_row.set_detail("✓ 已是最新版本")
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
