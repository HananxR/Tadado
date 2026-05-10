"""Data model for the calendar heatmap — loads daily task counts from repository."""

from __future__ import annotations

from datetime import date

from ...models.repository import TaskRepository


class HeatmapModel:
    """Loads and caches heatmap data (date -> task count) for a given year."""

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository
        self._data: dict[date, int] = {}
        self._max_count: int = 0
        self._current_year: int = date.today().year

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_year(self, year: int) -> None:
        """Load heatmap data for the given year from the repository."""
        self._data = self._repository.get_heatmap_data(year)
        self._max_count = max(self._data.values()) if self._data else 0
        self._current_year = year

    def count_for_date(self, d: date) -> int:
        """Return the task count for a specific date."""
        return self._data.get(d, 0)

    def max_count(self) -> int:
        """Return the maximum count across all dates in the current year."""
        return self._max_count

    def current_year(self) -> int:
        """Return the currently loaded year."""
        return self._current_year

    def color_level(self, d: date, colors: dict[str, str]) -> str:
        """Map a date's task count to a heatmap color level key (level_0 .. level_4)."""
        count = self.count_for_date(d)
        if count == 0:
            return "level_0"
        if self._max_count == 0:
            return "level_1"
        ratio = count / self._max_count
        if ratio <= 0.25:
            return "level_1"
        if ratio <= 0.5:
            return "level_2"
        if ratio <= 0.75:
            return "level_3"
        return "level_4"

    @property
    def data(self) -> dict[date, int]:
        return dict(self._data)
