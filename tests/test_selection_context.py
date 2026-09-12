"""Tests for SelectionContext — 跨视图共享选中上下文。"""

from __future__ import annotations

from src.ui.selection_context import SelectionContext


def _make(qapp):
    ctx = SelectionContext()
    return ctx


def test_defaults(qapp):
    ctx = _make(qapp)
    assert ctx.partition_id is None
    assert ctx.selected_task_id is None
    assert ctx.range == "week"


def test_set_partition_emits_once(qapp):
    ctx = _make(qapp)
    hits = []
    ctx.changed.connect(lambda: hits.append(1))
    ctx.set_partition("p1")
    ctx.set_partition("p1")  # 同值不发射
    assert ctx.partition_id == "p1"
    assert len(hits) == 1


def test_select_task_emits_on_change(qapp):
    ctx = _make(qapp)
    hits = []
    ctx.changed.connect(lambda: hits.append(1))
    ctx.select_task("t1")
    ctx.select_task("t2")
    assert ctx.selected_task_id == "t2"
    assert len(hits) == 2


def test_set_range(qapp):
    ctx = _make(qapp)
    hits = []
    ctx.changed.connect(lambda: hits.append(1))
    ctx.set_range("month")
    ctx.set_range("month")
    assert ctx.range == "month"
    assert len(hits) == 1
