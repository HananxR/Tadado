"""Partition model — named task groupings like OneNote notebooks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Partition:
    """A named category / notebook for grouping tasks."""

    id: str
    name: str
    sort_order: int = 0
    created_at: Optional[datetime] = None


DEFAULT_PARTITIONS = [
    "工作",
    "个人",
    "学习",
]
