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


class _GridTile(QPushButton):
    """2×2 等宽网格卡片：图标 + 标题 + 可选状态行，对称布局无宽度差."""

    def __init__(self, icon: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(72)
        t = get_tokens()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 20px; border: none; background: transparent;")
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {t.text_primary};"
            f"border: none; background: transparent;"
        )
        layout.addWidget(title_label)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            f"font-size: 10px; color: {t.text_secondary}; border: none;"
            f"background: transparent;"
        )
        layout.addWidget(self._status_label)

        self.setStyleSheet(
            f"QPushButton {{"
            f"  background: {t.surface_raised};"
            f"  border: 1px solid {t.border_primary};"
            f"  border-radius: 8px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: {t.bg_tertiary};"
            f"  border-color: {t.accent};"
            f"}}"
        )

    def set_status(self, text: str, color: str | None = None) -> None:
        t = get_tokens()
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"font-size: 10px; color: {color or t.text_secondary};"
            f"border: none; background: transparent;"
        )


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

        cat_colors = {"新增": t.success, "优化": t.warning, "修复": t.danger}

        for vi, ver in enumerate(versions):
            if vi:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet(f"QFrame {{ color: {t.border_primary}; }}")
                sep.setFixedHeight(1)
                layout.addWidget(sep)

            # 每个版本一个 QLabel，用 HTML <p> 段落统一控制行距与缩进
            # （QLabel 不支持 CSS line-height，逐条 QLabel 会导致行距不齐）
            parts = []
            date_html = (
                f"&nbsp;<span style='font-size:11px;font-weight:400;"
                f"color:{t.text_secondary};'>{ver['date']}</span>"
                if ver.get("date") else ""
            )
            parts.append(
                f'<p style="margin:14px 0 2px 0;font-size:15px;font-weight:700;'
                f'color:{t.text_primary};">v{ver["version"]}{date_html}</p>'
            )
            for cat, items in ver["categories"]:
                if not items:
                    continue
                color = cat_colors.get(cat, t.text_primary)
                parts.append(
                    f'<p style="margin:8px 0 2px 0;font-size:11px;font-weight:700;'
                    f'color:{color};">● {cat}</p>'
                )
                for item in items:
                    parts.append(
                        f'<p style="margin:3px 0 3px 12px;font-size:12px;'
                        f'color:{t.text_secondary};">· {_md_to_html(item, t)}</p>'
                    )
            section = QLabel("".join(parts))
            section.setWordWrap(True)
            section.setTextFormat(Qt.TextFormat.RichText)
            section.setOpenExternalLinks(True)
            layout.addWidget(section)

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
        self.setFixedWidth(420)
        self.resize(420, 520)
        self.setMinimumHeight(480)

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

        # ── 2×2 等宽网格卡片：对称布局，无宽度差异 ──
        from PySide6.QtWidgets import QGridLayout

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._check_tile = _GridTile("🔄", "检查更新")
        self._check_tile.clicked.connect(self._on_check_updates)
        grid.addWidget(self._check_tile, 0, 0)

        history_tile = _GridTile("📜", "版本更新记录")
        history_tile.clicked.connect(self._open_history)
        grid.addWidget(history_tile, 0, 1)

        github_tile = _GridTile("🌐", "GitHub Releases")
        github_tile.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(_GITHUB_RELEASES))
        )
        grid.addWidget(github_tile, 1, 0)

        aliyun_tile = _GridTile("☁️", "阿里云盘")
        aliyun_tile.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(ALIYUN_DRIVE_URL))
        )
        grid.addWidget(aliyun_tile, 1, 1)

        layout.addLayout(grid)
        layout.addSpacing(18)

        # ── 反馈行（小图标链接，居中） ──
        feedback = QLabel(
            f'<a href="mailto:hanxy8413@gmail.com" '
            f'style="color:{t.text_secondary}; text-decoration:none;">✉ 邮箱</a>'
            f'&nbsp;&nbsp;·&nbsp;&nbsp;'
            f'<span style="color:{t.text_secondary};">💬 Pyvan 公众号</span>'
            f'&nbsp;&nbsp;·&nbsp;&nbsp;'
            f'<a href="{_GITHUB_REPO}" '
            f'style="color:{t.text_secondary}; text-decoration:none;">GitHub</a>'
        )
        feedback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        feedback.setOpenExternalLinks(True)
        feedback.setStyleSheet("font-size: 11px;")
        layout.addWidget(feedback)
        layout.addStretch()

        # ── Copyright ──
        copyright_label = QLabel(
            f"Copyright © {datetime.now().year} HananxR · MIT License"
        )
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_label.setStyleSheet(f"font-size: 10px; color: {t.text_secondary};")
        layout.addWidget(copyright_label)

        outer.addWidget(content, 1)

    def _open_history(self) -> None:
        VersionHistoryDialog(self).exec()

    # ── Update check slots ────────────────────────────────────────

    def _on_check_updates(self) -> None:
        if self._update_checker is None:
            self._check_tile.set_status("不可用")
            return

        self._check_tile.setEnabled(False)
        self._check_tile.set_status("检查中…")
        self._update_checker.check_finished.connect(
            self._on_check_finished, type=Qt.ConnectionType.SingleShotConnection
        )
        self._update_checker.check_error.connect(
            self._on_check_error, type=Qt.ConnectionType.SingleShotConnection
        )
        self._update_checker.check_for_updates()

    def _on_check_finished(self, update_info: dict | None) -> None:
        t = get_tokens()
        self._check_tile.setEnabled(True)
        if update_info is None:
            self._check_tile.set_status("✓ 已是最新版本", t.success)
        else:
            self._update_info = update_info
            latest = update_info.get("latest_version", "")
            self._check_tile.set_status(f"发现新版本 {latest}", t.accent)

    def _on_check_error(self, message: str) -> None:
        t = get_tokens()
        self._check_tile.setEnabled(True)
        self._check_tile.set_status(message, t.danger)

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
