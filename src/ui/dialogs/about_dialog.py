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
    QTextBrowser,
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


class _RowLink(QPushButton):
    """左侧品牌栏方案的行链接：左标题 + 右状态/箭头，悬停强调色，细分割线."""

    def __init__(self, title: str, detail: str = "›", parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("aboutRowLink")
        t = get_tokens()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 13px; color: {t.text_primary}; border: none; background: transparent;"
        )
        layout.addWidget(title_label)
        layout.addStretch()

        self._detail = QLabel(detail)
        self._detail.setStyleSheet(
            f"font-size: 12px; color: {t.text_secondary}; border: none; background: transparent;"
        )
        layout.addWidget(self._detail)

        self.setStyleSheet(
            f"QPushButton#aboutRowLink {{"
            f"  border: none; background: transparent; text-align: left;"
            f"  border-bottom: 1px solid {t.border_primary};"
            f"}}"
            f"QPushButton#aboutRowLink:hover {{ background: transparent; }}"
        )
        self._title_label = title_label

    def set_detail(self, text: str, color: str | None = None) -> None:
        t = get_tokens()
        self._detail.setText(text)
        self._detail.setStyleSheet(
            f"font-size: 12px; color: {color or t.text_secondary};"
            f"border: none; background: transparent;"
        )

    def _hover_on(self) -> None:
        t = get_tokens()
        self._title_label.setStyleSheet(
            f"font-size: 13px; color: {t.accent}; border: none; background: transparent;"
        )

    def _hover_off(self) -> None:
        t = get_tokens()
        self._title_label.setStyleSheet(
            f"font-size: 13px; color: {t.text_primary}; border: none; background: transparent;"
        )

    def enterEvent(self, event) -> None:
        self._hover_on()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_off()
        super().leaveEvent(event)


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


class VersionHistoryDialog(QDialog):
    """独立滚动页：全版本更新记录，以帮助文档同款 HTML 风格渲染."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("版本更新记录")
        self.setObjectName("versionHistoryDialog")
        self.resize(480, 620)
        self.setMinimumSize(400, 480)

        t = get_tokens()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_HeaderBar("版本更新记录", self.reject))

        versions = _parse_changelog_md()
        if not versions:
            highlights = get_release_highlights()
            versions = [{
                "version": get_version_display(),
                "date": "",
                "categories": [(cat, list(items)) for cat, items in highlights.items() if items],
            }]

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setFrameShape(QFrame.Shape.NoFrame)
        browser.setStyleSheet(
            f"QTextBrowser {{ background: {t.bg_primary}; padding: 6px; }}"
        )
        browser.setHtml(self._build_html(versions, t))
        outer.addWidget(browser, 1)

    @staticmethod
    def _build_html(versions: list[dict], t) -> str:
        """构建帮助手册同款排版：版本 h2 + 分类 h3 + 无序列表."""
        cat_colors = {"新增": t.success, "优化": t.warning, "修复": t.danger}
        parts = ['<div style="margin:8px 6px 4px 6px;">']
        for ver in versions:
            date_html = (
                f'&nbsp;<span style="font-size:11px;font-weight:400;'
                f'color:{t.text_secondary};">{ver["date"]}</span>'
                if ver.get("date") else ""
            )
            parts.append(
                f'<h2 style="font-size:16px;font-weight:700;color:{t.text_primary};'
                f'margin:22px 0 2px 0;">v{ver["version"]}{date_html}</h2>'
            )
            parts.append(
                f'<hr style="border:none;border-top:2px solid {t.accent};'
                f'margin:4px 0 8px 0;">'
            )
            for cat, items in ver["categories"]:
                if not items:
                    continue
                color = cat_colors.get(cat, t.text_primary)
                parts.append(
                    f'<h3 style="font-size:12px;font-weight:700;color:{color};'
                    f'margin:12px 0 4px 0;">{cat}</h3>'
                )
                parts.append(
                    f'<ul style="margin:0 0 6px 0;color:{t.text_secondary};">'
                )
                for item in items:
                    parts.append(
                        f'<li style="font-size:12px;margin:4px 0;">'
                        f'{_md_to_html(item, t)}</li>'
                    )
                parts.append("</ul>")
        parts.append("</div>")
        return "".join(parts)

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
        self.setFixedSize(460, 400)

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

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ── 左侧品牌栏 ──
        side = QWidget()
        side.setObjectName("aboutSide")
        side.setFixedWidth(118)
        side.setStyleSheet(
            f"QWidget#aboutSide {{"
            f"  background: {t.bg_secondary};"
            f"  border-right: 1px solid {t.border_primary};"
            f"}}"
        )
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 28, 0, 0)
        side_layout.setSpacing(0)

        logo = QLabel()
        logo_path = self._find_icon("app_icon.svg")
        pix = QPixmap(logo_path) if logo_path else QPixmap()
        if not pix.isNull():
            pix = pix.scaled(
                46, 46,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(pix)
        else:
            logo.setText("✦")
            logo.setStyleSheet(f"font-size: 30px; color: {t.accent};")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(logo)
        side_layout.addSpacing(12)

        name = QLabel("Tadado")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {t.text_primary};")
        side_layout.addWidget(name)
        side_layout.addSpacing(3)

        ver = QLabel(f"v{get_version_display()}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"font-size: 11px; color: {t.text_secondary};")
        side_layout.addWidget(ver)
        side_layout.addStretch()

        body_layout.addWidget(side)

        # ── 右侧内容区 ──
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 20, 20, 16)
        content_layout.setSpacing(0)

        def _section(text: str) -> None:
            label = QLabel(text)
            label.setStyleSheet(
                f"font-size: 12px; color: {t.text_secondary};"
                f"padding-top: 14px; padding-bottom: 4px;"
            )
            content_layout.addWidget(label)

        def _row(title: str, detail: str = "›", clicked=None) -> _RowLink:
            row = _RowLink(title, detail)
            if clicked:
                row.clicked.connect(clicked)
            content_layout.addWidget(row)
            return row

        _section("服务")
        self._check_row = _row("检查更新", clicked=self._on_check_updates)
        _row("版本更新记录", clicked=self._open_history)

        _section("下载")
        _row("GitHub Releases", "↗",
             clicked=lambda: QDesktopServices.openUrl(QUrl(_GITHUB_RELEASES)))
        _row("阿里云盘", "↗",
             clicked=lambda: QDesktopServices.openUrl(QUrl(ALIYUN_DRIVE_URL)))

        _section("反馈")
        # 邮箱点击复制到剪贴板（不依赖系统邮件客户端）
        self._email_row = _row(
            "电子邮箱", "hanxy8413@gmail.com", clicked=self._copy_email
        )
        feedback = QLabel(
            f'<span style="color:{t.text_secondary};">💬 Pyvan</span>'
            f'&nbsp;&nbsp;·&nbsp;&nbsp;'
            f'<a href="{_GITHUB_REPO}" '
            f'style="color:{t.text_secondary}; text-decoration:none;">GitHub</a>'
        )
        feedback.setOpenExternalLinks(True)
        feedback.setStyleSheet("font-size: 11px;")
        content_layout.addWidget(feedback)

        content_layout.addStretch()

        copyright_label = QLabel(
            f"Copyright © {datetime.now().year} HananxR · MIT License"
        )
        copyright_label.setStyleSheet(f"font-size: 10px; color: {t.text_secondary};")
        content_layout.addWidget(copyright_label)

        body_layout.addWidget(content, 1)
        outer.addWidget(body, 1)

    def _open_history(self) -> None:
        VersionHistoryDialog(self).exec()

    def _copy_email(self) -> None:
        """复制邮箱地址到剪贴板，行尾提示已复制."""
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText("hanxy8413@gmail.com")
        self._email_row.set_detail("已复制 ✓", get_tokens().success)

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
            self._check_row.set_detail("✓ 已是最新版本", t.success)
        else:
            self._update_info = update_info
            latest = update_info.get("latest_version", "")
            self._check_row.set_detail(f"发现新版本 {latest}", t.accent)

    def _on_check_error(self, message: str) -> None:
        t = get_tokens()
        self._check_row.setEnabled(True)
        self._check_row.set_detail(message, t.danger)

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
