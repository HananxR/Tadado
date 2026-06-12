"""Centralized version source — single point of truth for the app version.

The canonical version lives here.  ``release.ps1`` sets the git tag from
the same value, and ``pyproject.toml`` should be kept in sync manually
(used only by the build backend).

Usage::

    from src.version import __version__, get_version_display

"""

from __future__ import annotations

__version__ = "0.2.0"


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

_RELEASE_HIGHLIGHTS: dict[str, dict[str, tuple[str, ...]]] = {
    "0.2.0": {
        "新增": (
            "状态下拉框即时刷新进度：切换至已完成→100，切回进行中→80",
        ),
        "优化": (
            "截止时间默认值对齐快速计算 23:59，创建任务预填当天日期",
            "快速计算标签：任务类型→时间粒度，临时→天",
        ),
        "修复": (
            "进度 100% 因列宽不足显示为 00",
            "多条状态→已完成路径遗漏进度=100 自动设定",
            "批量状态变更缺失 completed_at 和进度同步",
        ),
    },
    "0.1.2.4": {
        "修复": (
            "速览栏排除已完成已归档而非全部已完成",
            "阿里云盘更新检测支持 4 段版本号匹配",
        ),
    },
    "0.1.2.3": {
        "新增": (
            "关于对话框展示升级内容与下载渠道，更新结果内联反馈",
        ),
        "优化": (
            "提醒信息融入速览栏与进度栏被动展示，时间粒度细化至分钟",
            "欢迎页 Banner 动态适配分区状态",
            "更新检查优先阿里云盘",
        ),
        "修复": (
            "Banner 背景文字可读性",
            "启动遮罩期间鼠标转圈",
        ),
    },
    "0.1.2.2": {
        "新增": (
            "安装程序支持简体中文界面",
        ),
        "修复": (
            "安装程序中文乱码问题",
        ),
    },
    "0.1.2.1": {
        "新增": (
            "关于对话框检查更新与阿里云盘下载渠道",
            "联系方式与反馈渠道",
        ),
        "优化": (
            "关于对话框重新布局",
            "版本号统一为 4 位格式",
        ),
        "修复": (
            "进度栏时段筛选数据不一致",
            "进度栏与活动报告计数不匹配",
        ),
    },
}


def get_release_highlights(version: str | None = None) -> dict[str, tuple[str, ...]] | None:
    """Return categorized feature highlights for *version*, or ``None``.

    Returns a dict like ``{"新增": (...), "优化": (...), "修复": (...)}``.
    When *version* is omitted, the current ``__version__`` is used.
    """
    v = version or __version__
    return _RELEASE_HIGHLIGHTS.get(v)
