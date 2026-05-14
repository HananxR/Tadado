"""Markdown task line parser — extracts structured fields from raw Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..models.priority import Priority
from ..models.task_status import TaskStatus

# Pattern breakdown:
#   ^- \[([ xX])\]                          checkbox
#   \s+(TODO|DOING|DONE|URGENT|WAIT|LATER)   status keyword
#   (?:\s+\[#([ABC])\])?                     optional priority
#   (?:\s+<(\d{4}-\d{2}-\d{2})>)?            optional scheduled date
#   (?:\s+<(\d{4}-\d{2}-\d{2})>)?            optional deadline date
#   \s+(.+)$                                  title + tags

_TASK_LINE_PATTERN = re.compile(
    r"^-\s*\[([ xX])\]\s+"
    r"(TODO|DOING|DONE|URGENT|WAIT|LATER)"
    r"(?:\s+\[#([ABC])\])?"
    r"(?:\s+<(\d{4}-\d{2}-\d{2})>)?"
    r"(?:\s+<(\d{4}-\d{2}-\d{2})"
    r"(?:[T ](\d{2}:\d{2}))?>)?"
    r"\s+(.+)$"
)

_TAG_PATTERN = re.compile(r"#([\w一-鿿][\w/\-一-鿿]*)")

_STATUS_KEYWORDS = frozenset(s.value for s in TaskStatus)


@dataclass
class ParsedTask:
    """Structured result of parsing a single Markdown task line."""

    checkbox_checked: bool
    status: TaskStatus
    priority: Priority
    scheduled_date: Optional[date]
    deadline_date: Optional[date]
    deadline_time: Optional[str] = None
    title: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def clean_title(self) -> str:
        """Title with trailing tags stripped (for display)."""
        return _TAG_PATTERN.sub("", self.title).strip()


class MarkdownTaskParser:
    """Parses Markdown task lines into structured :class:`ParsedTask` objects."""

    def parse(self, md_line: str) -> ParsedTask:
        """Parse a single Markdown task line.

        Raises:
            ValueError: if the line cannot be parsed as a task.
        """
        line = md_line.strip()
        if not line:
            raise ValueError("Empty input")

        match = _TASK_LINE_PATTERN.match(line)
        if not match:
            # Fallback: try parsing with defaults for missing elements
            return self._fallback_parse(line)

        checkbox_char = match.group(1)
        status = TaskStatus.from_string(match.group(2))
        priority_str = match.group(3)
        priority = Priority.from_string(priority_str) if priority_str else Priority.NONE
        scheduled_date = self._parse_date_safe(match.group(4))
        deadline_date = self._parse_date_safe(match.group(5))
        deadline_time = match.group(6)
        title_text = match.group(7).strip()

        tags = self._extract_tags(title_text)
        clean_title = _TAG_PATTERN.sub("", title_text).strip()

        return ParsedTask(
            checkbox_checked=checkbox_char.lower() == "x",
            status=status,
            priority=priority,
            scheduled_date=scheduled_date,
            deadline_date=deadline_date,
            deadline_time=deadline_time,
            title=clean_title,
            tags=tags,
        )

    def parse_batch(self, md_text: str) -> list[tuple[Optional[ParsedTask], str, Optional[str]]]:
        """Parse multi-line Markdown text.

        Returns a list of (ParsedTask or None, original_line, error_message).
        Successful parses have ParsedTask; failures have None and an error string.
        """
        results: list[tuple[Optional[ParsedTask], str, Optional[str]]] = []
        for raw_line in md_text.strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = self.parse(line)
                results.append((parsed, raw_line, None))
            except ValueError as exc:
                results.append((None, raw_line, str(exc)))
        return results

    # ------------------------------------------------------------------
    # Fallback: parse minimal / malformed task lines
    # ------------------------------------------------------------------

    def _fallback_parse(self, line: str) -> ParsedTask:
        """Attempt to parse a line that doesn't match the strict pattern.

        Handles cases like:
        - Missing checkbox:  "TODO Buy groceries"
        - Missing keyword:   "- [ ] Buy groceries"
        - Plain text:         "Buy groceries"
        """
        status = TaskStatus.TODO
        checkbox = False
        priority = Priority.NONE
        scheduled_date = None
        deadline_date = None
        remaining = line

        # Strip leading list marker
        if remaining.startswith("- ["):
            checkbox_match = re.match(r"-\s*\[([ xX])\]\s*", remaining)
            if checkbox_match:
                checkbox = checkbox_match.group(1).lower() == "x"
                remaining = remaining[checkbox_match.end():]

        # Extract status keyword
        for kw in sorted(_STATUS_KEYWORDS, key=len, reverse=True):
            if remaining.upper().startswith(kw):
                status = TaskStatus.from_string(kw)
                remaining = remaining[len(kw):].strip()
                break

        # Extract priority
        pri_match = re.match(r"\[#([ABC])\]\s*", remaining, re.IGNORECASE)
        if pri_match:
            priority = Priority.from_string(pri_match.group(1))
            remaining = remaining[pri_match.end():].strip()

        # Extract dates with optional time (greedy, up to two)
        deadline_time = None
        date_matches = re.findall(
            r"<(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?>", remaining
        )
        if date_matches:
            scheduled_date = self._parse_date_safe(date_matches[0][0])
            remaining = re.sub(
                r"<\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2})?>", "", remaining, count=1
            ).strip()
        if len(date_matches) >= 2:
            deadline_date = self._parse_date_safe(date_matches[1][0])
            deadline_time = date_matches[1][1] if len(date_matches[1]) > 1 else None
            remaining = re.sub(
                r"<\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2})?>", "", remaining, count=1
            ).strip()

        tags = self._extract_tags(remaining)
        clean_title = _TAG_PATTERN.sub("", remaining).strip()
        if not clean_title:
            clean_title = remaining or "Untitled task"

        return ParsedTask(
            checkbox_checked=checkbox or (status == TaskStatus.DONE),
            status=status,
            priority=priority,
            scheduled_date=scheduled_date,
            deadline_date=deadline_date,
            deadline_time=deadline_time,
            title=clean_title,
            tags=tags,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tags(text: str) -> list[str]:
        """Extract unique tags from title text, preserving order."""
        tags = _TAG_PATTERN.findall(text)
        seen: set[str] = set()
        unique: list[str] = []
        for t in tags:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        return unique

    @staticmethod
    def _parse_date_safe(raw: Optional[str]) -> Optional[date]:
        """Parse a YYYY-MM-DD string, returning None on failure."""
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except (ValueError, TypeError):
            return None
