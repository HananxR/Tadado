"""AnalysisController —— 懒构建短路与导出解析（阶段 4）。"""

from __future__ import annotations

from src.ui.controllers.analysis_controller import AnalysisController


class TestBeforeAttach:
    """分析页是懒构建的：attach() 之前所有槽都必须安全短路。"""

    def test_is_not_attached_initially(self, qapp):
        ctrl = AnalysisController(None)
        assert ctrl.is_attached is False
        assert ctrl.date_range == (None, None)

    def test_slots_short_circuit(self, qapp):
        ctrl = AnalysisController(None)
        # 以下调用均不应抛异常
        ctrl.refresh()
        ctrl.refresh("p1")
        ctrl.on_period_changed(None, None, "")
        ctrl.on_tag_selected("标签")
        ctrl.on_prev()
        ctrl.on_next()
        ctrl.on_search_changed("关键词")
        assert ctrl.is_attached is False

    def test_date_range_updates_without_widgets(self, qapp):
        from datetime import date

        ctrl = AnalysisController(None)
        ctrl.on_period_changed(date(2026, 9, 1), date(2026, 9, 7), "本周")
        assert ctrl.date_range == (date(2026, 9, 1), date(2026, 9, 7))


class TestParseExportRows:
    def test_parses_title_status_progress_and_entries(self, qapp):
        ctrl = AnalysisController(None)
        text = "#标签\n1. 任务A [TODO, 30]:\n    进展一\n    进展二\n"

        rows = ctrl._parse_export_rows(text)

        assert rows == [(1, "任务A", "TODO", "30", "进展一\n进展二")]

    def test_skips_lines_without_entries(self, qapp):
        ctrl = AnalysisController(None)
        assert ctrl._parse_export_rows("1. 空任务 [DOING, 10]:\n") == []
