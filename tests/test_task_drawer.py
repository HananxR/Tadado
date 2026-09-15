"""TaskDrawer 测试 —— 维护抽屉（阶段 4）。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QPixmap

from src.models.repository import TaskRepository
from src.models.task_status import TaskStatus
from src.services.task_service import TaskService
from src.ui.drawer import TaskDrawer
from src.utils.signal_bus import get_signal_bus


@pytest.fixture
def drawer(tmp_path, qapp, qtbot):
    repo = TaskRepository(str(tmp_path / "drawer.db"))
    repo.open()
    svc = TaskService(repo, signal_bus=get_signal_bus())
    host = __import__("PySide6.QtWidgets", fromlist=["QWidget"]).QWidget()
    qtbot.addWidget(host)
    host.resize(900, 600)
    host.show()
    widget = TaskDrawer(svc, host, animate=False)
    yield widget, svc, repo, host
    widget.deleteLater()
    host.deleteLater()
    repo.close()


class TestOpenClose:
    def test_open_populates_fields(self, drawer):
        widget, svc, repo, host = drawer
        # 规范顺序：状态 → 日期 → 标题 → 标签（日期写在标题之后会被当成标题字面量）
        task = svc.create_task("- [ ] TODO <2026-12-31> 抽屉任务 #a")
        assert widget.open_task(task.id) is True
        assert widget.is_open is True
        assert widget.current_task is not None
        assert widget._title_label.text() == "抽屉任务"
        assert "#a" in widget._tags_edit.text()
        assert widget._status_combo.currentData() == task.status
        assert widget._log_list.count() >= 1  # 含"创建任务"记录

    def test_open_unknown_task_returns_false(self, drawer):
        widget, svc, repo, host = drawer
        assert widget.open_task("missing-id") is False
        assert widget.is_open is False

    def test_close_emits_closed(self, drawer):
        widget, svc, repo, host = drawer
        task = svc.create_task("- [ ] 待关闭 #c")
        widget.open_task(task.id)
        seen: list[int] = []
        widget.closed.connect(lambda: seen.append(1))
        widget.close_drawer()
        assert seen == [1]
        assert widget.is_open is False

    def test_escape_key_closes(self, drawer):
        widget, svc, repo, host = drawer
        task = svc.create_task("- [ ] Esc 关闭 #e")
        widget.open_task(task.id)
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        widget.keyPressEvent(event)
        assert widget.is_open is False

    def test_geometry_docks_right(self, drawer):
        widget, svc, repo, host = drawer
        widget.open_task(svc.create_task("- [ ] 停靠 #d").id)
        assert widget.x() == host.width() - widget.width()


class TestWrites:
    def test_append_activity(self, drawer):
        widget, svc, repo, host = drawer
        task = svc.create_task("- [ ] 记进展 #l")
        widget.open_task(task.id)
        before = len(svc.get_task(task.id).activity_log)

        widget._log_edit.setPlainText("完成初稿")
        widget._progress.setValue(45)
        widget._on_append_activity()

        fetched = svc.get_task(task.id)
        assert len(fetched.activity_log) == before + 1
        assert fetched.activity_log[-1]["content"] == "完成初稿"
        assert fetched.progress == 45
        assert widget._log_list.count() == before + 1
        assert widget._log_edit.toPlainText() == ""

    def test_append_activity_empty_is_rejected(self, drawer):
        widget, svc, repo, host = drawer
        task = svc.create_task("- [ ] 空进展 #l")
        widget.open_task(task.id)
        before = len(svc.get_task(task.id).activity_log)
        widget._log_edit.clear()
        widget._on_append_activity()
        assert len(svc.get_task(task.id).activity_log) == before

    def test_save_updates_task_and_closes(self, drawer):
        widget, svc, repo, host = drawer
        task = svc.create_task("- [ ] 原名 #t")
        widget.open_task(task.id)

        widget._md_edit.setPlainText("- [ ] 改名后 #t2")
        widget._tags_edit.setText("#新标签")
        widget._status_combo.setCurrentIndex(
            widget._status_combo.findData(TaskStatus.DONE)
        )
        widget._urgency_combo.setCurrentIndex(widget._urgency_combo.findData(1))

        seen: list[str] = []
        widget.saved.connect(seen.append)
        widget._on_save()

        fetched = svc.get_task(task.id)
        assert fetched.title == "改名后"
        assert fetched.tags == ["新标签"]
        assert fetched.status == TaskStatus.DONE
        assert fetched.progress == 100
        assert fetched.urgency == 1
        assert seen == [task.id]
        assert widget.is_open is False

    def test_save_rejects_empty_markdown(self, drawer):
        widget, svc, repo, host = drawer
        task = svc.create_task("- [ ] 保留原名 #t")
        widget.open_task(task.id)
        widget._md_edit.setPlainText("   ")
        widget._on_save()
        assert svc.get_task(task.id).title == "保留原名"
        assert widget.is_open is True


class TestRendering:
    def test_render_is_not_blank(self, drawer):
        widget, svc, repo, host = drawer
        widget.open_task(svc.create_task("- [ ] 渲染 #r").id)
        widget.resize(widget.width(), host.height())
        pixmap = QPixmap(widget.size())
        pixmap.fill()
        widget.render(pixmap)
        image = pixmap.toImage()
        colors = {
            image.pixel(x, y)
            for y in range(0, image.height(), 5)
            for x in range(0, image.width(), 5)
        }
        assert len(colors) > 2
