"""Markdown task line parser — extracts structured fields from raw Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..models.task_status import TaskStatus

# Pattern breakdown:
#   ^- \[([^\]]{0,3})\]                       priority bracket (0-3 chars)
#   \s+                                       mandatory whitespace
#   (?:(TODO|DOING|DONE|OVERDUE)\s+)?         optional status keyword (not in Markdown)
#   (?:\s*<(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?>)?  optional date 1 + time
#   (?:\s*<(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?>)?  optional date 2 + time
#   \s*(.+)$                                  title + tags

_TASK_LINE_PATTERN = re.compile(
    r"^-\s*\[([^\]]*)\]\s+"
    r"(?:(TODO|DOING|DONE|OVERDUE)\s+)?"
    r"(?:\s*<(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?>)?"
    r"(?:\s*<(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?>)?"
    r"\s*(.+)$"
)

# Tag pattern: # must be preceded by whitespace or start-of-string (not mid-word)
_TAG_PATTERN = re.compile(r"(?<!\S)#([\w一-鿿][\w/\-一-鿿]*)")

_STATUS_KEYWORDS = frozenset(s.value for s in TaskStatus)


@dataclass
class ParsedTask:
    """Structured result of parsing a single Markdown task line."""

    checkbox_checked: bool
    status: TaskStatus
    scheduled_date: Optional[date]
    deadline_date: Optional[date]
    deadline_time: Optional[str] = None
    title: str = ""
    tags: list[str] = field(default_factory=list)
    urgency: int = 3  # 0=紧急, 1=重要, 2=关注, 3=普通

    @property
    def clean_title(self) -> str:
        """Title with tags stripped (for display). Uses same logic as parse()."""
        result = self.title
        for tag in self.tags:
            result = re.sub(rf"\s*#{re.escape(tag)}\b", "", result, count=1)
        return result.strip()


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

        bracket_content = match.group(1).ljust(3)
        status_str = match.group(2)
        status = TaskStatus.from_string(status_str) if status_str else TaskStatus.TODO
        scheduled_date = self._parse_date_safe(match.group(3))
        first_time = match.group(4)
        deadline_date = self._parse_date_safe(match.group(5))
        deadline_time = match.group(6)
        # Single date logic:
        # - with time → always deadline
        # - without status keyword (new format) → deadline
        if deadline_date is None and scheduled_date is not None:
            if first_time or not status_str:
                deadline_date = scheduled_date
                deadline_time = first_time or deadline_time
                scheduled_date = None
        title_text = match.group(7).strip()

        tags = self._extract_tags(title_text)
        # Remove extracted tags from title (keep content #refs intact)
        clean_title = title_text
        for tag in tags:
            clean_title = re.sub(rf"\s*#{re.escape(tag)}\b", "", clean_title, count=1)
        clean_title = clean_title.strip()

        # Priority from bracket: count '*' (clamp 0-3)
        star_count = min(bracket_content.count('*'), 3)
        urgency = 3 - star_count if star_count > 0 else 3
        checkbox_checked = 'x' in bracket_content.lower()

        return ParsedTask(
            checkbox_checked=checkbox_checked,
            status=status,
            scheduled_date=scheduled_date,
            deadline_date=deadline_date,
            deadline_time=deadline_time,
            title=clean_title,
            tags=tags,
            urgency=urgency,
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
        scheduled_date = None
        deadline_date = None
        remaining = line

        # Strip leading list marker with priority bracket [*], [**], [***], [   ], [x]
        urgency = 3
        if remaining.startswith("- ["):
            checkbox_match = re.match(r"-\s*\[([^\]]*)\]\s*", remaining)
            if checkbox_match:
                bracket = checkbox_match.group(1)
                checkbox = 'x' in bracket.lower()
                star_count = min(bracket.count('*'), 3)
                urgency = 3 - star_count if star_count > 0 else 3
                remaining = remaining[checkbox_match.end():]

        # Extract status keyword
        for kw in sorted(_STATUS_KEYWORDS, key=len, reverse=True):
            if remaining.upper().startswith(kw):
                status = TaskStatus.from_string(kw)
                remaining = remaining[len(kw):].strip()
                break

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
        # Remove extracted tags from title (keep content #refs intact)
        clean_title = remaining
        for tag in tags:
            clean_title = re.sub(rf"\s*#{re.escape(tag)}\b", "", clean_title, count=1)
        clean_title = clean_title.strip()
        if not clean_title:
            clean_title = remaining or "Untitled task"

        return ParsedTask(
            checkbox_checked=checkbox or (status == TaskStatus.DONE),
            status=status,
            scheduled_date=scheduled_date,
            deadline_date=deadline_date,
            deadline_time=deadline_time,
            title=clean_title,
            tags=tags,
            urgency=urgency,
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
