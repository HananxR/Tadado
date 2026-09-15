"""Update __version__ in src/_version_data.py.

Usage: python pack_scripts/update_version.py 0.2.5
"""
import re
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/update_version.py <version>")
        sys.exit(1)

    new_ver = sys.argv[1]
    version_py = Path(__file__).resolve().parents[1] / "src" / "_version_data.py"
    content = version_py.read_text(encoding="utf-8")
    new_content = re.sub(
        r'__version__\s*=\s*"[^"]*"',
        f'__version__ = "{new_ver}"',
        content,
    )
    if new_content == content:
        print(f"WARNING: __version__ not found or already {new_ver}")
    else:
        version_py.write_text(new_content, encoding="utf-8")
        print(f"Updated __version__ = {new_ver}")


if __name__ == "__main__":
    main()
