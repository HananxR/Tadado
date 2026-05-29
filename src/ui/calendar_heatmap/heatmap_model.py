"""Data model for the calendar heatmap — loads daily task counts from repository, with tag filtering."""

from __future__ import annotations

from datetime import date, timedelta

from ...models.repository import TaskRepository


class HeatmapModel:
    """Loads and caches heatmap data (date -> task count) for a given year."""

    _NUM_LEVELS = 8  # level_0 (empty) + level_1..7 (gradient)

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository
        self._data: dict[date, int] = {}
        self._task_counts: dict[date, int] = {}
        self._max_count: int = 0
        self._current_year: int = date.today().year
        self._selected_tags: list[str] = []
        self._available_tags: list[str] = []
        self._per_tag_data: dict[str, dict[date, int]] = {}
        self._partition_id: str | None = None
    # ------------------------------------------------------------------
    # Public API — loading
    # ------------------------------------------------------------------

    def load_year(self, year: int, tags: list[str] | None = None) -> None:
        self._current_year = year
        tags = tags or self._selected_tags
        self._data, self._task_counts = self._repository.get_heatmap_activity_data(year, tags if tags else None, self._partition_id)
        self._max_count = max(self._data.values()) if self._data else 0

    def load_available_tags(self) -> None:
        self._available_tags = self._repository.get_all_tags(self._partition_id)

    def load_per_tag(self, year: int) -> None:
        self._available_tags = self._repository.get_all_tags(self._partition_id)
        self._per_tag_data.clear()
        for tag in self._available_tags:
            self._per_tag_data[tag] = self._repository.get_heatmap_activity_data(year, [tag], self._partition_id)[0]
        self._data, self._task_counts = self._repository.get_heatmap_activity_data(year, partition_id=self._partition_id)
        self._max_count = max(self._data.values()) if self._data else 0

    # ------------------------------------------------------------------
    # Public API — accessors
    # ------------------------------------------------------------------

    def data_for_tag(self, tag: str | None) -> dict[date, int]:
        if tag is None or tag == "__all__":
            return dict(self._data)
        return self._per_tag_data.get(tag, {})

    def count_for_date(self, d: date) -> int:
        return self._data.get(d, 0)

    def task_count_for_date(self, d: date) -> int:
        return self._task_counts.get(d, 0)

    def tag_breakdown_for_date(self, d: date) -> dict[str, int]:
        """Return per-tag task counts for a given date."""
        result: dict[str, int] = {}
        for tag, tag_data in self._per_tag_data.items():
            c = tag_data.get(d, 0)
            if c > 0:
                result[tag] = c
        return result

    def max_count(self) -> int:
        return self._max_count

    def current_year(self) -> int:
        return self._current_year

    def selected_tags(self) -> list[str]:
        return list(self._selected_tags)

    def set_tags(self, tags: list[str]) -> None:
        self._selected_tags = list(tags)
        self.load_year(self._current_year)

    def set_partition_id(self, partition_id: str | None) -> None:
        self._partition_id = partition_id

    def available_tags(self) -> list[str]:
        return list(self._available_tags)

    @property
    def data(self) -> dict[date, int]:
        return dict(self._data)

    # ------------------------------------------------------------------
    # Color leveling — 8-level log-scale bucketing
    # ------------------------------------------------------------------

    def color_level(self, count: int, max_count: int) -> str:
        """Map a count to a heatmap level key (level_0 .. level_7)."""
        if count == 0:
            return "level_0"
        if max_count == 0:
            return "level_1"
        ratio = count / max_count
        if ratio <= 0.01:
            return "level_1"
        if ratio <= 0.05:
            return "level_2"
        if ratio <= 0.12:
            return "level_3"
        if ratio <= 0.25:
            return "level_4"
        if ratio <= 0.45:
            return "level_5"
        if ratio <= 0.70:
            return "level_6"
        return "level_7"

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def total_count(self) -> int:
        return sum(self._data.values())

    def active_days(self) -> int:
        return sum(1 for v in self._data.values() if v > 0)

    def longest_streak(self) -> int:
        sorted_dates = sorted(self._data.keys())
        max_streak = cur = 0
        prev: date | None = None
        for d in sorted_dates:
            if self._data[d] > 0:
                if prev is None or d == prev + timedelta(days=1):
                    cur += 1
                else:
                    cur = 1
                max_streak = max(max_streak, cur)
                prev = d
            else:
                cur = 0
                prev = None
        return max_streak

    def current_streak(self) -> int:
        """Consecutive active days ending today (or yesterday if today has no tasks)."""
        today = date.today()
        streak = 0
        d = today
        while self._data.get(d, 0) > 0:
            streak += 1
            d -= timedelta(days=1)
        if streak == 0:
            # Allow streak to end yesterday
            d = today - timedelta(days=1)
            while self._data.get(d, 0) > 0:
                streak += 1
                d -= timedelta(days=1)
        return streak

    def daily_average(self) -> float:
        days = self.active_days()
        return self.total_count() / days if days > 0 else 0.0

    def monthly_count(self, year: int, month: int) -> int:
        return sum(c for d, c in self._data.items() if d.year == year and d.month == month)

    def weekly_count(self, year: int, week: int) -> int:
        return sum(c for d, c in self._data.items()
                   if d.isocalendar()[0] == year and d.isocalendar()[1] == week)
