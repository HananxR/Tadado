"""HeatmapModel —— 查询缓存与失效（阶段 7 性能项）。"""

from __future__ import annotations

from src.ui.calendar_heatmap.heatmap_model import HeatmapModel


class _CountingRepo:
    """包装真实仓库，统计两个重查询方法的调用次数。"""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.year_calls = 0
        self.tag_calls = 0

    def get_heatmap_activity_data(self, *args, **kwargs):
        self.year_calls += 1
        return self._inner.get_heatmap_activity_data(*args, **kwargs)

    def get_all_tags(self, *args, **kwargs):
        self.tag_calls += 1
        return self._inner.get_all_tags(*args, **kwargs)


class TestHeatmapCache:
    def test_load_year_hits_cache(self, repository):
        repo = _CountingRepo(repository)
        model = HeatmapModel(repo)

        model.load_year(2026)
        model.load_year(2026)

        assert repo.year_calls == 1

    def test_invalidate_forces_requery(self, repository):
        repo = _CountingRepo(repository)
        model = HeatmapModel(repo)

        model.load_year(2026)
        model.invalidate()
        model.load_year(2026)

        assert repo.year_calls == 2

    def test_partition_is_part_of_cache_key(self, repository):
        repo = _CountingRepo(repository)
        model = HeatmapModel(repo)

        model.load_year(2026)  # partition=None
        model.set_partition_id("p1")
        model.load_year(2026)  # 新 key → 重新查询
        model.load_year(2026)  # 命中缓存

        assert repo.year_calls == 2

    def test_available_tags_cached(self, repository):
        repo = _CountingRepo(repository)
        model = HeatmapModel(repo)

        model.load_available_tags()
        model.load_available_tags()

        assert repo.tag_calls == 1
