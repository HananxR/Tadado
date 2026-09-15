"""win32_hotkey 测试 —— parse_accel 纯函数 + 平台分支（阶段 5）。"""

from __future__ import annotations

import sys

import pytest

from src.utils import win32_hotkey as hk

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


def test_modifier_constants():
    assert hk.MOD_ALT == 0x1
    assert hk.MOD_CONTROL == 0x2
    assert hk.MOD_SHIFT == 0x4
    assert hk.MOD_WIN == 0x8


def test_hotkey_message_constant():
    assert hk.HOTKEY_MESSAGE == 0x0312


# ---------------------------------------------------------------------------
# parse_accel —— 合法输入
# ---------------------------------------------------------------------------


def test_ctrl_shift_space():
    assert hk.parse_accel("Ctrl+Shift+Space") == (hk.MOD_CONTROL | hk.MOD_SHIFT, 0x20)


def test_lowercase_alt_f4():
    assert hk.parse_accel("alt+F4") == (hk.MOD_ALT, 0x73)


def test_win_d():
    assert hk.parse_accel("Win+D") == (hk.MOD_WIN, 0x44)


def test_ctrl_alt_digit():
    assert hk.parse_accel("Ctrl+Alt+1") == (hk.MOD_CONTROL | hk.MOD_ALT, 0x31)


def test_f12_no_modifier():
    assert hk.parse_accel("F12") == (0, 0x7B)


def test_ctrl_enter():
    assert hk.parse_accel("Ctrl+Enter") == (hk.MOD_CONTROL, 0x0D)


def test_case_insensitive():
    assert hk.parse_accel("cTrL+ShIfT+sPaCe") == hk.parse_accel("CTRL+SHIFT+SPACE")


def test_order_independent():
    assert hk.parse_accel("Shift+Ctrl+Space") == hk.parse_accel("Ctrl+Shift+Space")
    assert hk.parse_accel("Space+Shift+Ctrl") == hk.parse_accel("Ctrl+Shift+Space")


def test_single_modifier():
    assert hk.parse_accel("Shift+A") == (hk.MOD_SHIFT, 0x41)


def test_all_modifiers_bit_or():
    assert hk.parse_accel("Ctrl+Alt+Shift+Win+A") == (
        hk.MOD_CONTROL | hk.MOD_ALT | hk.MOD_SHIFT | hk.MOD_WIN,
        0x41,
    )


@pytest.mark.parametrize(
    "accel, vk",
    [
        ("A", 0x41),
        ("Z", 0x5A),
        ("0", 0x30),
        ("9", 0x39),
        ("Space", 0x20),
        ("Enter", 0x0D),
        ("Tab", 0x09),
        ("Esc", 0x1B),
        ("Escape", 0x1B),
        ("Backspace", 0x08),
        ("Delete", 0x2E),
        ("Insert", 0x2D),
        ("Home", 0x24),
        ("End", 0x23),
        ("PageUp", 0x21),
        ("PageDown", 0x22),
        ("Up", 0x26),
        ("Down", 0x28),
        ("Left", 0x25),
        ("Right", 0x27),
    ],
)
def test_key_lookup(accel, vk):
    assert hk.parse_accel(accel) == (0, vk)


@pytest.mark.parametrize("n, vk", [(1, 0x70), (12, 0x7B), (24, 0x87)])
def test_function_keys(n, vk):
    assert hk.parse_accel(f"F{n}") == (0, vk)


# ---------------------------------------------------------------------------
# parse_accel —— 非法输入
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "accel",
    [
        "",
        "   ",
        "Ctrl+Shift",  # 只有修饰键
        "Ctrl+Foo",  # 未知键名
        "Hyper+A",  # 未知修饰键
        "Ctrl++A",  # 多余 +
        "Ctrl+A+",  # 尾部 +
        "+A",  # 头部 +
        "Ctrl+A+B",  # 多个主键
        "F0",  # F 键越界
        "F25",  # F 键越界
    ],
)
def test_invalid_raises_value_error(accel):
    with pytest.raises(ValueError):
        hk.parse_accel(accel)


def test_non_string_input_raises():
    with pytest.raises(ValueError):
        hk.parse_accel(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 平台分支
# ---------------------------------------------------------------------------


def test_is_supported_returns_bool():
    result = hk.is_supported()
    assert isinstance(result, bool)
    assert result == (sys.platform == "win32")


def test_register_hotkey_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert hk.register_hotkey("Ctrl+Shift+Space", lambda: None) is False


def test_unregister_hotkey_non_windows_noop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert hk.unregister_hotkey() is None


def test_register_hotkey_invalid_accel_returns_false():
    """非法加速器在触达 Win32 之前即失败，任何平台都返回 False（无副作用）。"""
    assert hk.register_hotkey("Ctrl+Foo", lambda: None) is False
    assert hk.current_accel() is None
