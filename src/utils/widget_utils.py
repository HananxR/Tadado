"""Shared widget sizing utilities."""

from __future__ import annotations


def combo_width(max_chars: int, font_size: int = 12) -> int:
    """QComboBox fixed width from max character count.
    Chinese char ≈ font_size px, dropdown ≈ 18px, padding 8+8=16px, border 1+1=2px."""
    return max_chars * font_size + 18 + 16 + 2
