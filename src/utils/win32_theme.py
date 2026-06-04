"""Win32 DWM helpers for per-window dark title bar support.

On Windows 10 1809+ the Desktop Window Manager accepts
DWMWA_USE_IMMERSIVE_DARK_MODE to toggle a dark title bar on a
per-window basis.  On Windows 11 a precise caption colour can also
be set via DWMWA_CAPTION_COLOR so dialog title bars match the
custom menu-bar area.

All functions are no-ops on non-Windows platforms.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


def is_dark_mode_supported() -> bool:
    """Return True when the OS supports per-window dark title bars.

    Requires Windows 10 build 17763 (RS5 / 1809) or later.
    """
    if sys.platform != "win32":
        return False
    try:
        _major, _minor, build = _get_windows_version()
        return build >= 17763
    except Exception:
        return False


def is_caption_color_supported() -> bool:
    """Return True when the OS supports a custom title-bar colour.

    Requires Windows 11 build 22000 or later.
    """
    if sys.platform != "win32":
        return False
    try:
        _major, _minor, build = _get_windows_version()
        return build >= 22000
    except Exception:
        return False


def set_window_dark_mode(
    widget: QWidget, dark: bool, caption_color: str | None = None
) -> bool:
    """Apply (or remove) a dark title bar on *widget*.

    When *caption_color* is given (a ``#RRGGBB`` hex string) and the
    OS is Windows 11+, the title bar is tinted to that exact colour
    via DWMWA_CAPTION_COLOR.

    Returns True when at least the dark-mode toggle succeeded.
    """
    if sys.platform != "win32":
        return False
    if not is_dark_mode_supported():
        return False
    try:
        hwnd = int(widget.winId())
        ok = _set_immersive_dark_mode(hwnd, dark)
        if dark and caption_color and is_caption_color_supported():
            _set_caption_color(hwnd, caption_color)
        return ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WIN_VERSION: tuple[int, int, int] | None = None


def _get_windows_version() -> tuple[int, int, int]:
    """Return (major, minor, build) via ntdll.RtlGetVersion.

    RtlGetVersion is unaffected by application manifest compatibility
    shims, unlike the kernel32 GetVersionEx API.
    """
    global _WIN_VERSION
    if _WIN_VERSION is not None:
        return _WIN_VERSION

    import ctypes

    class _OSVERSIONINFOW(ctypes.Structure):
        _fields_ = [
            ("dwOSVersionInfoSize", ctypes.c_ulong),
            ("dwMajorVersion", ctypes.c_ulong),
            ("dwMinorVersion", ctypes.c_ulong),
            ("dwBuildNumber", ctypes.c_ulong),
            ("dwPlatformId", ctypes.c_ulong),
            ("szCSDVersion", ctypes.c_wchar * 128),
        ]

    info = _OSVERSIONINFOW()
    info.dwOSVersionInfoSize = ctypes.sizeof(info)
    ntdll = ctypes.WinDLL("ntdll.dll")
    ntdll.RtlGetVersion(ctypes.byref(info))
    _WIN_VERSION = (info.dwMajorVersion, info.dwMinorVersion, info.dwBuildNumber)
    return _WIN_VERSION


def _hex_to_colorref(hex_color: str) -> int:
    """Convert ``#RRGGBB`` to a COLORREF DWORD (0x00BBGGRR)."""
    rgb = hex_color.lstrip("#")
    r, g, b = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)
    return (b << 16) | (g << 8) | r  # 0x00BBGGRR


def _set_immersive_dark_mode(hwnd: int, dark: bool) -> bool:
    """Call DwmSetWindowAttribute with DWMWA_USE_IMMERSIVE_DARK_MODE.

    The attribute constant varies by Windows build:
      * 20  – Windows 10 20H1 (build 19041) and later / Windows 11
      * 19  – Windows 10 RS5 (build 17763) through 1909
    """
    import ctypes

    _, _, build = _get_windows_version()
    attr = 20 if build >= 19041 else 19

    dwmapi = ctypes.WinDLL("dwmapi.dll")
    value = ctypes.c_int(1 if dark else 0)
    hr = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd),
        ctypes.c_ulong(attr),
        ctypes.byref(value),
        ctypes.sizeof(value),
    )
    return hr == 0  # S_OK


def _set_caption_color(hwnd: int, hex_color: str) -> bool:
    """Call DwmSetWindowAttribute with DWMWA_CAPTION_COLOR (35).

    Requires Windows 11 build 22000+.
    """
    import ctypes

    DWMWA_CAPTION_COLOR = 35
    colorref = ctypes.c_ulong(_hex_to_colorref(hex_color))
    dwmapi = ctypes.WinDLL("dwmapi.dll")
    hr = dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd),
        ctypes.c_ulong(DWMWA_CAPTION_COLOR),
        ctypes.byref(colorref),
        ctypes.sizeof(colorref),
    )
    return hr == 0
