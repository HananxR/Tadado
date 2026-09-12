"""任务管理页（page2）构建 — 纯移动自 MainWindow._build_page2（Phase 1）。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def build(mw) -> QWidget:
    """Build Task Management Console page — delegated to BatchController."""
    return mw._batch_ctrl.build_page()
