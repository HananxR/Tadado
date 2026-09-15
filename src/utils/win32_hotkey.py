"""Win32 全局热键 —— 纯函数解析 + Win32 注册/注销。

本模块只做两件事：

1. :func:`parse_accel` —— **纯函数**，把形如 ``"Ctrl+Shift+Space"`` 的加速器字符串
   解析成 ``(modifiers, vk)``；不依赖任何 Win32 API，跨平台可测。
2. :func:`register_hotkey` / :func:`unregister_hotkey` —— 仅 Windows 生效，内部用
   ``ctypes`` 调用 ``RegisterHotKey`` / ``UnregisterHotKey``。

模块顶层**不会** ``import ctypes.wintypes``，也不调用任何 Win32 API；``ctypes``
只在函数内的 Windows 分支里延迟导入。

WM_HOTKEY 消息消费约定
----------------------
``RegisterHotKey`` 以 ``None`` 作为窗口句柄注册，因此 ``WM_HOTKEY``
（= :data:`HOTKEY_MESSAGE`，0x0312）会投递到**注册线程的消息队列**：

* 调用方（WindowShell / ``QAbstractNativeEventFilter``）必须在**注册热键的同一线程**
  上消费该消息；
* 原生事件过滤器收到 ``msgType == HOTKEY_MESSAGE`` 时自行触发回调 —— 本模块只负责
  「解析 + 注册/注销」，不创建任何 QObject，也不负责消息循环。
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: ``RegisterHotKey`` 的修饰键位标志
MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4
MOD_WIN = 0x8

#: 本模块固定使用的热键 ID（``RegisterHotKey`` 第二个参数）
HOTKEY_ID = 1

#: ``WM_HOTKEY`` 消息号，调用方的原生事件过滤器据此识别热键消息
HOTKEY_MESSAGE = 0x0312

_MODIFIER_ALIASES: dict[str, int] = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
    "super": MOD_WIN,
    "meta": MOD_WIN,
}

_NAMED_KEYS: dict[str, int] = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "back": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}

#: 当前已注册的加速器与回调（强引用，避免回调被 GC 回收）
_current_accel: Optional[str] = None
_current_callback: Optional[Callable[[], None]] = None


# ---------------------------------------------------------------------------
# 纯函数：解析
# ---------------------------------------------------------------------------

def _resolve_vk(token: str) -> int:
    """把单个按键名解析成虚拟键码（VK）；未知键名抛 ``ValueError``。"""
    t = token.lower()
    if t in _NAMED_KEYS:
        return _NAMED_KEYS[t]
    if len(t) == 1 and "a" <= t <= "z":
        return 0x41 + (ord(t) - ord("a"))
    if len(t) == 1 and "0" <= t <= "9":
        return 0x30 + (ord(t) - ord("0"))
    if len(t) >= 2 and t[0] == "f" and t[1:].isdigit():
        n = int(t[1:])
        if 1 <= n <= 24:
            return 0x70 + (n - 1)
    raise ValueError(f"未知按键名: {token!r}")


def parse_accel(accel: str) -> tuple[int, int]:
    """把快捷键字符串解析为 ``(modifiers, vk)``（纯函数，跨平台可测）。

    形如 ``"Ctrl+Shift+Space"`` / ``"alt+F4"`` / ``"Win+D"`` / ``"F12"``；
    大小写不敏感，修饰键顺序无关。

    ``modifiers`` 为 ``MOD_ALT | MOD_CONTROL | MOD_SHIFT | MOD_WIN`` 的位或；
    ``vk`` 为虚拟键码（无修饰键时 ``modifiers`` 为 0）。

    Raises:
        ValueError: 空串、只有修饰键、未知键名、未知修饰键、多余的 ``+``、
            多个主键、非字符串输入。
    """
    if not isinstance(accel, str):
        raise ValueError(f"快捷键必须是字符串，收到 {type(accel).__name__}")
    raw = accel.strip()
    if not raw:
        raise ValueError("快捷键字符串为空")

    parts = [p.strip() for p in raw.split("+")]
    if any(p == "" for p in parts):
        raise ValueError(f"非法的快捷键（多余的 '+' 或空键名）: {accel!r}")

    modifiers = 0
    vk: Optional[int] = None
    for part in parts:
        low = part.lower()
        if low in _MODIFIER_ALIASES:
            modifiers |= _MODIFIER_ALIASES[low]
            continue
        if vk is not None:
            raise ValueError(f"快捷键包含多个主键: {accel!r}")
        vk = _resolve_vk(part)

    if vk is None:
        raise ValueError(f"快捷键只有修饰键，缺少主键: {accel!r}")
    return modifiers, vk


# ---------------------------------------------------------------------------
# 平台能力
# ---------------------------------------------------------------------------

def is_supported() -> bool:
    """当前平台是否支持全局热键（仅 Windows 返回 True）。"""
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# Win32 注册 / 注销（仅 Windows 生效）
# ---------------------------------------------------------------------------

def register_hotkey(accel: str, callback: Callable[[], None]) -> bool:
    """注册全局热键；成功返回 True，失败返回 False（不抛异常）。

    * 非 Windows：直接返回 False，且不导入任何 Win32 相关模块；
    * 解析失败或 ``RegisterHotKey`` 返回 0：返回 False；
    * 重复注册：先 :func:`unregister_hotkey` 注销旧的。

    ``callback`` 仅被保存强引用；按键消息的捕获与分发由调用方负责（见模块
    docstring 的 WM_HOTKEY 说明）。
    """
    if sys.platform != "win32":
        return False

    try:
        modifiers, vk = parse_accel(accel)
    except ValueError:
        return False

    unregister_hotkey()

    try:
        import ctypes

        user32 = ctypes.WinDLL("user32.dll")  # type: ignore[attr-defined]
        ok = user32.RegisterHotKey(None, HOTKEY_ID, modifiers, vk)
    except Exception:
        return False

    if not ok:
        return False

    global _current_accel, _current_callback
    _current_accel = accel
    _current_callback = callback
    return True


def unregister_hotkey() -> None:
    """注销由 :func:`register_hotkey` 注册的热键（幂等，非 Windows 为空操作）。"""
    global _current_accel, _current_callback
    _current_accel = None
    _current_callback = None

    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32.dll")  # type: ignore[attr-defined]
        user32.UnregisterHotKey(None, HOTKEY_ID)
    except Exception:
        return


def current_accel() -> Optional[str]:
    """返回已成功注册的加速器字符串（未注册时为 None）。"""
    return _current_accel
