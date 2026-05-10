"""Priority enumeration with display helpers."""

from enum import IntEnum
from typing import Optional


class Priority(IntEnum):
    """Task priority levels matching Todoseq [#A]/[#B]/[#C] convention."""

    NONE = 0
    C = 1
    B = 2
    A = 3

    @property
    def display_tag(self) -> str:
        """Markdown priority token string, e.g. '[#A]' or ''."""
        if self == Priority.NONE:
            return ""
        return f"[#{self.name}]"

    @property
    def display_color(self) -> str:
        """Hex color for priority badges."""
        _color_map = {
            Priority.A: "#e74c3c",
            Priority.B: "#f39c12",
            Priority.C: "#3498db",
            Priority.NONE: "#95a5a6",
        }
        return _color_map[self]

    @classmethod
    def from_string(cls, value: Optional[str]) -> "Priority":
        """Parse a single-letter priority string. Returns NONE for invalid input."""
        if not value:
            return cls.NONE
        upper = value.strip().upper()
        if upper in ("A", "B", "C"):
            return cls[upper]
        return cls.NONE

    @classmethod
    def from_level(cls, level: int) -> "Priority":
        """Create from an integer level 0-3."""
        try:
            return cls(level)
        except ValueError:
            return cls.NONE
