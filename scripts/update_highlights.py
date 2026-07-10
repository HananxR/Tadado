"""Update _RELEASE_HIGHLIGHTS in src/version.py from CHANGELOG.md.

Usage: python scripts/update_highlights.py [version]
  If version is omitted, uses the current __version__ from src/version.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
VERSION_PY = PROJECT_ROOT / "src" / "_version_data.py"

CAT_MAP = {"Added": "新增", "Changed": "优化", "Fixed": "修复"}


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_changelog(version: str) -> dict[str, tuple[str, ...]] | None:
    """Extract highlights for *version* from CHANGELOG.md."""
    text = read_file(CHANGELOG)
    # Find the version section header: "## [X.Y.Z] — YYYY-MM-DD"
    pattern = rf"## \[{re.escape(version)}\].*?\n\n(.*?)(?=\n## \[|$)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        print(f"ERROR: Version [{version}] not found in CHANGELOG.md")
        return None

    body = match.group(1)
    highlights: dict[str, tuple[str, ...]] = {}
    current_cat: str | None = None

    for line in body.split("\n"):
        # Category header: "### Added" etc.
        m = re.match(r"###\s+(\w+)", line)
        if m:
            eng = m.group(1)
            current_cat = CAT_MAP.get(eng)
            continue
        # Bullet point: "- **key**: description" or "- description"
        if current_cat and line.startswith("- "):
            item = line[2:].strip()
            # Strip bold markers **...** from the key portion
            item = re.sub(r"\*\*(.+?)\*\*[：:]\s*", r"\1: ", item)
            # Convert backticks to <code> for QLabel RichText
            item = re.sub(r"`([^`]+)`", r"<code>\1</code>", item)
            highlights.setdefault(current_cat, []).append(item)

    return {k: tuple(v) for k, v in highlights.items()} if highlights else None


def write_highlights(version: str, highlights: dict[str, tuple[str, ...]]) -> None:
    """Rewrite _RELEASE_HIGHLIGHTS in the data file with only *version*."""
    content = read_file(VERSION_PY)
    # Build the Python dict literal — the only entry
    lines = [f'    "{version}": {{']
    for cat in ("新增", "优化", "修复"):
        if cat in highlights:
            items = ",\n            ".join(f'"{item}"' for item in highlights[cat])
            lines.append(f'        "{cat}": (\n            {items},\n        ),')
    lines.append("    },")
    new_block = "\n".join(lines)

    # Replace everything from _RELEASE_HIGHLIGHTS to end-of-file
    m = re.search(r"^_RELEASE_HIGHLIGHTS\s*:.*", content, re.MULTILINE)
    if not m:
        print("ERROR: _RELEASE_HIGHLIGHTS not found")
        sys.exit(1)

    header = "_RELEASE_HIGHLIGHTS: dict[str, dict[str, tuple[str, ...]]] = {"
    content = content[: m.start()] + header + "\n" + new_block + "\n}\n"

    VERSION_PY.write_text(content, encoding="utf-8")
    print(f"Updated _RELEASE_HIGHLIGHTS for {version}")


def main() -> None:
    # Determine version
    if len(sys.argv) > 1:
        version = sys.argv[1].lstrip("v")
    else:
        sys.path.insert(0, str(PROJECT_ROOT))
        from src._version_data import __version__

        version = __version__

    highlights = parse_changelog(version)
    if highlights is None:
        sys.exit(1)

    write_highlights(version, highlights)


if __name__ == "__main__":
    main()
