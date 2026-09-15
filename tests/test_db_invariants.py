"""DB 保全不变量测试 — 2.0 界面重构全程零 DB 变更的守门测试。

TODO(阶段1收尾) 的「DB 保全抽查」：``PRAGMA user_version`` 恒为 8，
且 ``raw_md`` 作为规范数据源在 create → format → parse 往返后保持稳定。
"""

from __future__ import annotations

from src.models.repository import TaskRepository
from src.models.task import Task
from src.services.task_service import TaskService
from src.utils.signal_bus import SignalBus

EXPECTED_SCHEMA_VERSION = 8


def test_schema_version_is_8(repository: TaskRepository) -> None:
    """打开数据库后 migrations 必须停在 v8（2.0 重构期间无迁移）。"""
    version = repository.conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == EXPECTED_SCHEMA_VERSION


def test_required_columns_present(repository: TaskRepository) -> None:
    """重构不得增删任务表列（raw_md / activity_log / urgency 等）。"""
    cols = {row[1] for row in repository.conn.execute("PRAGMA table_info(tasks)")}
    required = {
        "id",
        "raw_md",
        "title",
        "status",
        "tags",
        "deadline_date",
        "deadline_time",
        "scheduled_date",
        "created_at",
        "updated_at",
        "archived",
        "partition_id",
        "activity_log",
        "progress",
        "suspended",
        "urgency",
    }
    assert required <= cols


def test_raw_md_round_trip_stable(temp_db, qapp) -> None:
    """抽查 3 条任务的 raw_md：create → format → parse → format 字面量不变。"""
    repo = TaskRepository(temp_db)
    repo.open()
    try:
        svc = TaskService(repo, signal_bus=SignalBus())

        cases = [
            "- [ ] <2026-12-31 23:59> 年度总结 #工作 #复盘",
            "- [ ] 重构任务服务 #架构",
            "- [***] <2026-06-15> 紧急修复 #bug",
        ]
        assert len(cases) == 3

        for raw in cases:
            task = svc.create_task(raw)
            stored = svc.get_task(task.id)
            assert stored is not None
            # 入库后的 raw_md 是规范形式，必须与内存对象一致
            assert stored.raw_md == task.raw_md

            # 往返稳定：parse(format(task)) 再 format 得到同一字面量
            reparsed = svc.parse_markdown(stored.raw_md)
            rebuilt = svc.format_task(
                Task(
                    id=task.id,
                    raw_md="",
                    title=reparsed.title,
                    status=reparsed.status,
                    tags=reparsed.tags,
                    deadline_date=reparsed.deadline_date,
                    deadline_time=reparsed.deadline_time,
                    scheduled_date=reparsed.scheduled_date,
                    urgency=reparsed.urgency,
                )
            )
            assert rebuilt == stored.raw_md
    finally:
        repo.close()
