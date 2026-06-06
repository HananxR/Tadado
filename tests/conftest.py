"""Shared pytest fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.models.repository import TaskRepository


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
