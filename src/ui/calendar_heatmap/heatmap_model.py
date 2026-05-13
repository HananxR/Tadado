"""Data model for the calendar heatmap — loads daily task counts from repository, with tag filtering."""

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
        self._selected_tags: list[str] = []  # empty = all tags
        self._available_tags: list[str] = []
        self._per_tag_data: dict[str, dict[date, int]] = {}  # tag -> date -> count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_year(self, year: int, tags: list[str] | None = None) -> None:
        """Load heatmap data for the given year, optionally filtered by tags."""
        self._current_year = year
        tags = tags or self._selected_tags
        self._data = self._repository.get_heatmap_data(year, tags if tags else None)
        self._max_count = max(self._data.values()) if self._data else 0

    def load_available_tags(self) -> None:
        """Refresh the list of all available tags."""
        self._available_tags = self._repository.get_all_tags()

    def load_per_tag(self, year: int) -> None:
        """Preload heatmap data for each tag independently."""
        self._available_tags = self._repository.get_all_tags()
        self._per_tag_data.clear()
        for tag in self._available_tags:
            self._per_tag_data[tag] = self._repository.get_heatmap_data(year, [tag])
        # Also load combined
        self._data = self._repository.get_heatmap_data(year)
        self._max_count = max(self._data.values()) if self._data else 0

    def data_for_tag(self, tag: str | None) -> dict[date, int]:
        """Return heatmap data for a specific tag, or combined if tag is None."""
        if tag is None or tag == "__all__":
            return dict(self._data)
        return self._per_tag_data.get(tag, {})

    def count_for_date(self, d: date) -> int:
        """Return the task count for a specific date (based on current filter)."""
        return self._data.get(d, 0)

    def max_count(self) -> int:
        """Return the maximum count across all dates in the current year."""
        return self._max_count

    def current_year(self) -> int:
        """Return the currently loaded year."""
        return self._current_year

    def selected_tags(self) -> list[str]:
        return list(self._selected_tags)

    def set_tags(self, tags: list[str]) -> None:
        self._selected_tags = list(tags)
        self.load_year(self._current_year)

    def available_tags(self) -> list[str]:
        return list(self._available_tags)

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
