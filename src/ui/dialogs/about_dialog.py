"""About dialog — WeChat-style about page + dedicated version-history page.

Main page (fixed height, fully controlled layout):
    brand block (icon / name / version / tagline) + hairline menu rows.
Version history lives in its own scrollable dialog, opened from a menu row
— the main page never grows unpredictably.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
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


def _md_to_html(text: str) -> str:
    """CHANGELOG Markdown 片段 → 富文本（加粗/行内代码/链接，颜色走文档 CSS）."""
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 兼容历史条目里写死的 <code> 标签
    safe = safe.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
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


_CHANGELOG_DOC_CSS = """
  :root {
    --bg: #f6f4ef; --surface: #fdfcf8; --text: #3a3832;
    --text-2: #6f6a5f; --accent: #4d57c3; --border: #e3dfd4;
    --success: #2f9e63; --warning: #d97f26; --danger: #c4453c;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1b1c26; --surface: #272835; --text: #d8d5c9;
      --text-2: #9d988b; --accent: #7c83ea; --border: #32333f;
      --success: #3fae7c; --warning: #e0963f; --danger: #e06c63;
    }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg); color: var(--text);
    font-family: "Microsoft YaHei", "Segoe UI", "Noto Sans SC", sans-serif;
    font-size: 14px; line-height: 1.75; max-width: 780px;
    margin: 0 auto; padding: 40px 32px 64px;
  }
  h1 { font-size: 24px; font-weight: 700; text-align: center; margin-bottom: 6px; }
  h1 + p { text-align: center; color: var(--text-2); font-size: 13px; margin-bottom: 36px; }
  h2 {
    font-size: 17px; font-weight: 700; margin-top: 30px; margin-bottom: 6px;
    padding-bottom: 6px; border-bottom: 2px solid var(--accent);
  }
  h2 .date { font-size: 12px; font-weight: 400; color: var(--text-2); margin-left: 8px; }
  h3 { font-size: 13px; font-weight: 700; margin-top: 14px; margin-bottom: 4px; }
  .cat-new { color: var(--success); }
  .cat-opt { color: var(--warning); }
  .cat-fix { color: var(--danger); }
  ul { margin: 4px 0 10px 20px; color: var(--text-2); }
  li { margin: 4px 0; font-size: 13px; }
  code {
    font-family: "Cascadia Code", "Consolas", monospace; font-size: 12px;
    background: var(--surface); border: 1px solid var(--border);
    padding: 1px 5px; border-radius: 3px; color: var(--text);
  }
  a { color: var(--accent); text-decoration: none; }
"""


def _changelog_doc_path() -> str:
    """生成独立版本记录 HTML 文件（临时目录，浏览器渲染），返回路径."""
    import tempfile

    versions = load_version_versions()
    parts = []
    for ver in versions:
        date_span = (
            f'<span class="date">{ver["date"]}</span>'
            if ver.get("date") else ""
        )
        parts.append(f"<h2>v{ver['version']}{date_span}</h2>")
        for cat, items in ver["categories"]:
            if not items:
                continue
            cls = {"新增": "cat-new", "优化": "cat-opt", "修复": "cat-fix"}.get(cat, "")
            parts.append(f'<h3 class="{cls}">{cat}</h3><ul>')
            for item in items:
                parts.append(f"<li>{_md_to_html(item)}</li>")
            parts.append("</ul>")
    body = "".join(parts)
    doc = (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
        "<title>Tadado 版本更新记录</title>"
        f"<style>{_CHANGELOG_DOC_CSS}</style></head><body>"
        "<h1>Tadado 版本更新记录</h1>"
        f"<p>Less Noise, More Done · 共 {len(versions)} 个版本</p>"
        f"{body}</body></html>"
    )
    path = Path(tempfile.gettempdir()) / "tadado_changelog.html"
    path.write_text(doc, encoding="utf-8")
    return str(path)


def load_version_versions() -> list[dict]:
    """解析 CHANGELOG.md；不可用时回退当前版本 highlights."""
    versions = _parse_changelog_md()
    if not versions:
        highlights = get_release_highlights()
        versions = [{
            "version": get_version_display(),
            "date": "",
            "categories": [(cat, list(items)) for cat, items in highlights.items() if items],
        }]
    return versions


class AboutPage(QWidget):
    """关于内容页（方案 D 左侧品牌栏）— 嵌入设置对话框的「关于」页签."""

    def __init__(
        self,
        parent: QWidget | None = None,
        update_checker: UpdateChecker | None = None,
    ) -> None:
        super().__init__(parent)
        self._update_checker = update_checker
        self._update_info: dict | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = get_tokens()

        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

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

        body.addWidget(side)

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
        # 版本更新记录与帮助文档：点击后调用本地浏览器呈现
        _row("版本更新记录", "↗", clicked=self._open_changelog_browser)
        _row("帮助文档", "↗", clicked=self._open_help_browser)

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

        body.addWidget(content, 1)

    def _open_changelog_browser(self) -> None:
        """生成版本记录 HTML 后用本地浏览器打开."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(_changelog_doc_path()))

    def _open_help_browser(self) -> None:
        """用本地浏览器打开帮助文档 manual.html."""
        import sys

        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
        path = base / "resources" / "help" / "manual.html"
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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
