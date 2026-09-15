"""Shared pytest fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.models.repository import TaskRepository


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication（offscreen）— SignalBus/UI 测试共用。

    覆盖 pytest-qt 自带同名 fixture：统一 offscreen 平台，无头环境可跑。
    Qt 禁止 QApplication 与 QCoreApplication 并存——若已有裸 QCoreApplication
    实例则直接报错，暴露违规创建点（见 tests/test_cli.py 的历史教训）。
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    elif not isinstance(app, QApplication):
        raise RuntimeError("已有 QCoreApplication 实例，QWidget 测试无法运行")
    return app


@pytest.fixture
def temp_db() -> str:
    """Create a temporary SQLite database for tests."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_tadado_")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def repository(temp_db: str) -> TaskRepository:
    """Return an opened TaskRepository backed by a temp database."""
    repo = TaskRepository(temp_db)
    repo.open()
    yield repo
    repo.close()


@pytest.fixture
def sample_tasks_dir(tmp_path: Path) -> Path:
    """Create a temp directory for export/import tests."""
    return tmp_path


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    """无头兜底：模态对话框会永久阻塞，统一短路为默认返回值。

    ``QMessageBox.exec()`` / ``QFileDialog.get*()`` 在 offscreen 平台无人可点，
    会让用例挂死（曾导致全量 ``pytest`` 300s 超时）。这里把常见入口替换为
    「确定 / 取消」结果，只让被测代码路径继续跑通，不做任何真实交互。
    """
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    _ok = QMessageBox.StandardButton.Ok
    _no = QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: _ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: _ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: _ok))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: _no))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", ""))
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", ""))
    )
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "")
    )
