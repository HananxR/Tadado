"""TaskDialog 回归测试 — 覆盖阶段 2 修复的「幻影 ``_signal_bus`` 必崩」。

历史 bug：新建分支在已发出 ``task_created`` 之后又访问不存在的
``self._signal_bus`` → 每次通过 TaskDialog 新建任务必抛 AttributeError。
"""

from __future__ import annotations

import pytest

from src.models.repository import TaskRepository
from src.services.task_service import TaskService
from src.ui.dialogs.task_dialog import TaskDialog
from src.utils.signal_bus import SignalBus


@pytest.fixture
def repo(temp_db):
    r = TaskRepository(temp_db)
    r.open()
    yield r
    r.close()


def test_create_task_does_not_crash(repo, qapp):
    """新建任务不得抛出 AttributeError（原「幻影 _signal_bus」回归）。"""
    svc = TaskService(repo, signal_bus=SignalBus())
    dlg = TaskDialog(svc)
    dlg._md_edit.setText("- [ ] 新任务 #标签")
    dlg._on_accept()  # 不应抛异常

    titles = [t.title for t in repo.get_all()]
    assert "新任务" in titles


def test_create_task_with_service_emits_created_once(repo, qapp):
    """service 路径：新建只发一次 task_created（不重复发信号）。"""
    bus = SignalBus()
    svc = TaskService(repo, signal_bus=bus)
    created: list[str] = []
    updated: list[str] = []
    bus.task_created.connect(lambda t: created.append(t.id))
    bus.task_updated.connect(lambda t: updated.append(t.id))

    dlg = TaskDialog(svc)
    dlg._md_edit.setText("- [ ] 服务新任务 #标签")
    dlg._on_accept()

    assert len(created) == 1
    assert not updated
    assert svc.get_task(created[0]) is not None


def test_edit_task_with_service_emits_updated_once(repo, qapp):
    """编辑已有任务：标题变更只发一次 task_updated。"""
    bus = SignalBus()
    svc = TaskService(repo, signal_bus=bus)
    task = svc.create_task("- [ ] 原标题 #标签")

    updated: list[str] = []
    status_changed: list[tuple] = []
    bus.task_updated.connect(lambda t: updated.append(t.id))
    bus.task_status_changed.connect(lambda t, old: status_changed.append((t.id, old)))

    dlg = TaskDialog(svc, task=svc.get_task(task.id))
    dlg._md_edit.setText("- [ ] 新标题 #标签")
    dlg._on_accept()

    assert updated == [task.id]
    assert not status_changed
    assert svc.get_task(task.id).title == "新标题"
