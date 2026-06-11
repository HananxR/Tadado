"""Centralized version source — single point of truth for the app version.

The canonical version lives here.  ``release.ps1`` sets the git tag from
the same value, and ``pyproject.toml`` should be kept in sync manually
(used only by the build backend).

Usage::

    from src.version import __version__, get_version_display

"""

from __future__ import annotations

__version__ = "0.1.2.3"


def get_version() -> str:
    """Return the raw semver string, e.g. ``"0.1.2.1"``."""
    return __version__


def get_version_display() -> str:
    """Return the user-facing version string, e.g. ``"v0.1.2.1"``."""
    return f"v{__version__}"


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string like ``"v1.2.3"`` or ``"1.2.3.1"`` into a
    variable-length tuple. 3-digit versions are padded to 4 for comparison."""
    clean = version_str.lstrip("v").strip()
    parts = clean.split(".")
    if len(parts) < 3 or len(parts) > 4:
        raise ValueError(f"Invalid version format: {version_str!r}")
    # Pad 3-digit → 4 for comparison: "0.1.0" → (0,1,0,0)
    while len(parts) < 4:
        parts.append("0")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


# ------------------------------------------------------------------
# Release highlights — user-facing feature summaries per version
# ------------------------------------------------------------------

_RELEASE_HIGHLIGHTS: dict[str, tuple[str, ...]] = {
    "0.1.2.3": (
        "速览栏与进度栏被动提醒，时间粒度细化至分钟",
        "关于对话框显示升级内容与下载渠道，检查更新结果内联",
        "欢迎页 Banner 动态适配分区状态，遮罩文字可读性优化",
        "更新检查优先阿里云盘，启动时消除转圈光标",
    ),
    "0.1.2.2": (
        "安装程序支持简体中文界面",
        "修复安装程序中文乱码问题",
    ),
    "0.1.2.1": (
        "关于对话框支持检查更新，推荐最佳下载渠道",
        "新增阿里云盘下载渠道，方便国内用户获取更新",
        "修复进度栏时段筛选数据不一致的问题",
    ),
}


def get_release_highlights(version: str | None = None) -> tuple[str, ...] | None:
    """Return user-facing feature highlights for *version*, or ``None``.

    When *version* is omitted, the current ``__version__`` is used.
    """
    v = version or __version__
    return _RELEASE_HIGHLIGHTS.get(v)
