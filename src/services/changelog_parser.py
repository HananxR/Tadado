"""Parse CHANGELOG.md to extract version-specific entries."""

from __future__ import annotations

import re
from pathlib import Path


def _changelog_path() -> Path | None:
    """Locate CHANGELOG.md — works both dev and PyInstaller frozen modes."""
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / "CHANGELOG.md"
    else:
        p = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
    return p if p.exists() else None


def get_version_changelog(version: str) -> dict | None:
    """Parse CHANGELOG.md and return the entry for *version*.

    Returns a dict with keys ``version``, ``date``, and ``sections``,
    or ``None`` if the file is missing or the version isn't found.
    """
    path = _changelog_path()
    if path is None:
        return None

    content = path.read_text(encoding="utf-8")
    # Find the version section: ## [X.Y.Z.W] — YYYY-MM-DD
    pattern = rf"^## \[{re.escape(version)}\] — (.+?)$\n(.*?)(?=\n## \[|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        # Try without date: ## [X.Y.Z.W]
        pattern2 = rf"^## \[{re.escape(version)}\].*?$\n(.*?)(?=\n## \[|\Z)"
        match = re.search(pattern2, content, re.MULTILINE | re.DOTALL)
        if not match:
            return None
        date_str = ""
        body = match.group(1).strip()
    else:
        date_str = match.group(1).strip()
        body = match.group(2).strip()

    sections: dict[str, list[str]] = {}
    current_section = ""
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("### "):
            current_section = stripped[4:].strip()
            sections[current_section] = []
        elif stripped.startswith("- ") and current_section:
            sections[current_section].append(stripped[2:].strip())
        elif stripped.startswith("- ") and not current_section:
            # Items before any section header → "其他"
            sections.setdefault("其他", []).append(stripped[2:].strip())

    if not sections:
        return None

    return {"version": version, "date": date_str, "sections": sections}


# ------------------------------------------------------------------
# HTML formatting
# ------------------------------------------------------------------

_SECTION_ICONS = {
    "Added": "✨ 新增",
    "Changed": "🔧 变更",
    "Fixed": "🐛 修复",
    "Removed": "🗑 移除",
    "Deprecated": "⚠ 弃用",
    "Security": "🔒 安全",
}


def format_changelog_html(entry: dict) -> str:
    """Format a changelog entry as compact HTML suitable for the about dialog."""
    sections = entry.get("sections", {})
    if not sections:
        return ""

    version = entry.get("version", "")
    date_str = entry.get("date", "")
    header = f"📋 更新日志 (v{version})"
    if date_str:
        header += f" · {date_str}"

    lines = [f'<p style="margin:0;font-size:12px;font-weight:700;">{header}</p>']

    for section_name in ("Added", "Changed", "Fixed", "Removed", "Deprecated", "Security"):
        items = sections.get(section_name, [])
        if not items:
            continue
        icon = _SECTION_ICONS.get(section_name, f"• {section_name}")
        for item in items:
            # Escape HTML in changelog content
            safe_item = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(
                f'<span style="font-size:11px;">'
                f'  <span style="font-weight:600;">{icon}</span>'
                f'  {safe_item}'
                f'</span><br/>'
            )

    # Fallback: any unknown sections
    for section_name, items in sections.items():
        if section_name in _SECTION_ICONS:
            continue
        for item in items:
            safe_item = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(
                f'<span style="font-size:11px;">'
                f'  <span style="font-weight:600;">• {section_name}</span>'
                f'  {safe_item}'
                f'</span><br/>'
            )

    return "".join(lines)
