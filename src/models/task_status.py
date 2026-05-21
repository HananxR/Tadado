"""Task status enumeration with state-cycle rules and display metadata."""

from enum import Enum


class TaskStatus(Enum):
    """Task state keywords matching the Todoseq / Org-mode convention.

    Five primary statuses. OVERDUE is auto-set when deadline passes;
    it is locked from manual changes — only modifying the deadline can
    revert it back to TODO.
    """

    OVERDUE = "OVERDUE"
    DOING = "DOING"
    TODO = "TODO"
    DONE = "DONE"

    @property
    def next_status(self) -> "TaskStatus":
        """Primary next state in the click-to-cycle graph."""
        _next_map = {
            TaskStatus.TODO: TaskStatus.DOING,
            TaskStatus.DOING: TaskStatus.DONE,
            TaskStatus.DONE: TaskStatus.DOING,
            TaskStatus.OVERDUE: TaskStatus.OVERDUE,
        }
        return _next_map[self]

    @property
    def display_name(self) -> str:
        """Human-readable name for UI labels."""
        _display_map = {
            TaskStatus.OVERDUE: "逾期",
            TaskStatus.DOING: "进行中",
            TaskStatus.TODO: "待办",
            TaskStatus.DONE: "已完成",
        }
        return _display_map[self]

    @property
    def display_color(self) -> str:
        """Hex color for status badges."""
        _color_map = {
            TaskStatus.OVERDUE: "#c0392b",
            TaskStatus.DOING: "#f39c12",
            TaskStatus.TODO: "#3498db",
            TaskStatus.DONE: "#2ecc71",
        }
        return _color_map[self]

    @property
    def checkbox_char(self) -> str:
        """Markdown checkbox character."""
        return "x" if self == TaskStatus.DONE else " "

    @classmethod
    def from_string(cls, value: str) -> "TaskStatus":
        """Case-insensitive lookup from a keyword string. Defaults to TODO."""
        upper = value.upper().strip()
        for member in cls:
            if member.value == upper:
                return member
        return cls.TODO
