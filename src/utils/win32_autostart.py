"""Windows auto-start registry helpers.

Manages the ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
registry key so Tadado can launch on user logon.

All functions are no-ops on non-Windows platforms.
"""

from __future__ import annotations

import sys

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Tadado"


def is_autostart_enabled() -> bool:
    """Return True when Tadado is registered for auto-start."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY)
        winreg.QueryValueEx(key, _VALUE_NAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    """Add or remove Tadado from the Windows Run registry key."""
    if sys.platform != "win32":
        return
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        )
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except OSError:
                pass  # already removed
        winreg.CloseKey(key)
    except OSError:
        pass


def _startup_command() -> str:
    """Build the command line that the Run registry key will execute."""
    if _is_frozen():
        return sys.executable
    # Dev mode: pythonw.exe (no console) + main.py absolute path
    from pathlib import Path

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    main_py = Path(__file__).resolve().parents[2] / "main.py"
    return f'"{pythonw}" "{main_py}"'


def _is_frozen() -> bool:
    """Return True when running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False) or "__compiled__" in dir(sys))
