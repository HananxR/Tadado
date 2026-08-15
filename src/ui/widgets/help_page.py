"""帮助文档页 — 以主题令牌渲染 manual.html，嵌入设置「帮助文档」页签."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from ...utils.design_tokens import get_tokens


def _manual_path() -> Path | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    p = base / "resources" / "help" / "manual.html"
    return p if p.exists() else None


class HelpPage(QWidget):
    """manual.html 的内嵌渲染（CSS 变量替换为当前主题令牌）."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = get_tokens()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            f"QTextBrowser {{ background: {t.bg_primary};"
            f" border: 1px solid {t.border_primary};"
            f" border-radius: 8px; padding: 8px; }}"
        )
        browser.document().setDefaultStyleSheet(self._build_css(t))

        path = _manual_path()
        if path is not None:
            html = path.read_text(encoding="utf-8")
            m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
            body_html = m.group(1) if m else html
            body_html = re.sub(r"<style.*?</style>", "", body_html, flags=re.S)
            body_html = re.sub(r"<script.*?</script>", "", body_html, flags=re.S)
            browser.setHtml(body_html)
        else:
            browser.setPlainText("帮助文档文件缺失。")

        layout.addWidget(browser)

    @staticmethod
    def _build_css(t) -> str:
        """manual.html 类名的紧凑样式表（QTextBrowser 支持的 CSS 子集）."""
        return (
            f"body {{ color:{t.text_primary}; font-size:13px; }}"
            f"h1 {{ font-size:20px; font-weight:700; color:{t.text_primary}; }}"
            f"h2 {{ font-size:16px; font-weight:600; color:{t.accent};"
            f" margin-top:18px; margin-bottom:6px; }}"
            f"h3 {{ font-size:14px; font-weight:600; color:{t.text_primary};"
            f" margin-top:12px; margin-bottom:4px; }}"
            f"p {{ color:{t.text_secondary}; margin:6px 0; }}"
            f"ul, ol {{ color:{t.text_secondary}; margin:4px 0 8px 16px; }}"
            f"li {{ margin:2px 0; }}"
            f"a {{ color:{t.accent}; text-decoration:none; }}"
            f"code {{ color:{t.text_primary}; background:{t.bg_secondary}; }}"
            f"pre {{ background:{t.bg_secondary}; margin:8px 0; padding:6px 8px; }}"
            f"kbd {{ border:1px solid {t.border_primary}; background:{t.bg_secondary}; }}"
            f"table {{ margin:8px 0; }}"
            f"th {{ font-weight:600; background:{t.bg_secondary}; padding:4px 8px; }}"
            f"td {{ color:{t.text_secondary}; padding:4px 8px; }}"
            f".tip {{ background:{t.bg_secondary}; color:{t.text_primary};"
            f" border-left:3px solid {t.accent}; margin:8px 0; padding:6px 10px; }}"
            f".warn {{ background:{t.danger_bg}; color:{t.text_primary};"
            f" border-left:3px solid {t.warning}; margin:8px 0; padding:6px 10px; }}"
            f".toc {{ background:{t.bg_secondary}; margin:8px 0; padding:6px 10px; }}"
        )
