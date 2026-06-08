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

# DWMWA_CLOAK (13): 隐藏窗口使其对 DWM 合成器不可见（Windows 8+）
# 用于启动期间完全隐藏窗口，准备就绪后再解除，消除启动残影
_DWMWA_CLOAK = 13

# DWMWA_NCRENDERING_POLICY (2): 控制非客户区渲染策略
# DWMNCRP_DISABLED (1): 完全禁用 NC 渲染，包括标题栏按钮
# 从根源消除原生 NC 标题栏按钮的残影闪现
_DWMWA_NCRENDERING_POLICY = 2
_DWMNCRP_DISABLED = 1


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


def is_cloak_supported() -> bool:
    """Return True when the OS supports DWMWA_CLOAK.

    Requires Windows 8 build 9200 or later.
    """
    if sys.platform != "win32":
        return False
    try:
        _major, _minor, build = _get_windows_version()
        return build >= 9200
    except Exception:
        return False


def set_window_cloaked(widget: QWidget, cloaked: bool) -> bool:
    """Hide (*cloaked*) or reveal the window from the DWM compositor.

    When *cloaked* is True the window is still composed by DWM but not
    rendered, making the window completely invisible during startup setup.
    Use this together with ``WA_DontShowOnScreen`` for defence-in-depth
    against startup flicker on frameless windows.

    Requires Windows 8+ (build 9200).  Returns True on success.
    """
    if sys.platform != "win32":
        return False
    if not is_cloak_supported():
        return False
    try:
        import ctypes

        hwnd = int(widget.winId())
        dwmapi = ctypes.WinDLL("dwmapi.dll")
        value = ctypes.c_int(1 if cloaked else 0)
        hr = dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_ulong(_DWMWA_CLOAK),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return hr == 0  # S_OK
    except Exception:
        return False


def set_window_nc_rendering_disabled(widget: QWidget) -> bool:
    """Disable DWM non-client rendering for *widget*.

    Prevents DWM from drawing native title-bar buttons (minimize /
    maximize / close) on frameless windows, eliminating the startup
    "ghost buttons" flash on Windows 11.

    Requires Windows 8+ (build 9200).  Returns True on success.
    """
    if sys.platform != "win32":
        return False
    if not is_cloak_supported():
        return False
    try:
        import ctypes

        hwnd = int(widget.winId())
        dwmapi = ctypes.WinDLL("dwmapi.dll")
        value = ctypes.c_int(_DWMNCRP_DISABLED)
        hr = dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_ulong(_DWMWA_NCRENDERING_POLICY),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return hr == 0  # S_OK
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


def enable_window_snap(widget: QWidget) -> bool:
    """Add WS_THICKFRAME | WS_CAPTION to the underlying HWND style.

    ``FramelessWindowHint`` removes these styles, which also disables
    Windows Aero Snap (left/right docking, quarter-screen, maximise-via-drag).
    Adding them back restores Snap while ``DWMWA_NCRENDERING_POLICY =
    DWMNCRP_DISABLED`` (set separately) prevents DWM from actually painting
    the native title bar.

    Call after ``winId()`` has created the HWND and before ``show()``.
    Returns True on success.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        GWL_STYLE = -16
        WS_THICKFRAME = 0x00040000
        WS_CAPTION = 0x00C00000
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020

        user32 = ctypes.WinDLL("user32.dll")
        hwnd = int(widget.winId())

        style = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_STYLE)
        if style == 0:
            return False

        new_style = style | WS_THICKFRAME | WS_CAPTION
        user32.SetWindowLongW(ctypes.c_void_p(hwnd), GWL_STYLE, new_style)

        user32.SetWindowPos(
            ctypes.c_void_p(hwnd),
            ctypes.c_void_p(0),  # HWND_TOP = 0 after insert-after
            ctypes.c_int(0),
            ctypes.c_int(0),
            ctypes.c_int(0),
            ctypes.c_int(0),
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
        return True
    except Exception:
        return False
