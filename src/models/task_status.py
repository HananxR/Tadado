"""Task status enumeration with state-cycle rules and display metadata."""

from enum import Enum


class TaskStatus(Enum):
    """Task state keywords matching the Todoseq / Org-mode convention."""

    TODO = "TODO"
    DOING = "DOING"
    DONE = "DONE"
    URGENT = "URGENT"
    WAIT = "WAIT"
    LATER = "LATER"

    @property
    def next_status(self) -> "TaskStatus":
        """Primary next state in the click-to-cycle graph."""
        _next_map = {
            TaskStatus.TODO: TaskStatus.DOING,
            TaskStatus.URGENT: TaskStatus.DOING,
            TaskStatus.DOING: TaskStatus.DONE,
            TaskStatus.DONE: TaskStatus.TODO,
            TaskStatus.WAIT: TaskStatus.DOING,
            TaskStatus.LATER: TaskStatus.TODO,
        }
        return _next_map[self]

    @property
    def display_name(self) -> str:
        """Human-readable name for UI labels."""
        _display_map = {
            TaskStatus.TODO: "待办",
            TaskStatus.DOING: "进行中",
            TaskStatus.DONE: "已完成",
            TaskStatus.URGENT: "紧急",
            TaskStatus.WAIT: "等待中",
            TaskStatus.LATER: "稍后",
        }
        return _display_map[self]

    @property
    def display_color(self) -> str:
        """Hex color for status badges."""
        _color_map = {
            TaskStatus.TODO: "#3498db",
            TaskStatus.DOING: "#f39c12",
            TaskStatus.DONE: "#2ecc71",
            TaskStatus.URGENT: "#e74c3c",
            TaskStatus.WAIT: "#9b59b6",
            TaskStatus.LATER: "#95a5a6",
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
